"""Unit tests for webhook management, matrix bots, and authentication use cases."""

from uuid import uuid4

import pytest

from slack2tchap.application.dtos import (
    CreateWebhookCommand,
    RegisterMatrixAccountCommand,
    SendPublicWebhookCommand,
)
from slack2tchap.application.use_cases import (
    AuthenticateApiKeyUseCase,
    CreateWebhookUseCase,
    DeleteMatrixAccountUseCase,
    DeleteUserUseCase,
    DeleteWebhookUseCase,
    ListMatrixAccountsUseCase,
    ProcessPublicWebhookUseCase,
    RegisterMatrixAccountUseCase,
)
from slack2tchap.domain.exceptions import (
    DomainError,
    InvalidApiKeyError,
    MatrixAccountNotFoundError,
    UserNotFoundError,
    WebhookNotFoundError,
)
from slack2tchap.domain.models import (
    AlertMessage,
    AlertSeverity,
    MatrixAccount,
    User,
    WebhookEndpoint,
)
from slack2tchap.domain.ports import SecretCipherPort
from slack2tchap.infrastructure.security.api_key import hash_api_key
from tests.conftest import (
    FakeMatrixAccountRepository,
    FakeMatrixClientManager,
    FakeMatrixMessenger,
    FakeUserRepository,
    FakeWebhookRepository,
)


@pytest.mark.asyncio
async def test_register_and_list_matrix_accounts(
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    secret_cipher: SecretCipherPort,
) -> None:
    user_id = uuid4()
    register_uc = RegisterMatrixAccountUseCase(fake_matrix_account_repository, secret_cipher)

    account_dto = await register_uc.execute(
        RegisterMatrixAccountCommand(
            name="Bot Supervision",
            matrix_user_id="@bot-sup:agent.tchap.gouv.fr",
            user_id=user_id,
            password="secure_matrix_password_123",
        )
    )

    assert account_dto.name == "Bot Supervision"
    assert account_dto.matrix_user_id == "@bot-sup:agent.tchap.gouv.fr"
    assert account_dto.user_id == user_id
    assert account_dto.device_id.startswith("s2t_")

    # Verify password was encrypted at rest
    saved = await fake_matrix_account_repository.get_by_id(account_dto.id)
    assert saved is not None
    assert saved.encrypted_password is not None
    assert saved.encrypted_password != "secure_matrix_password_123"
    assert saved.encryption_nonce is not None

    decrypted = secret_cipher.decrypt(saved.encrypted_password, saved.encryption_nonce)
    assert decrypted == "secure_matrix_password_123"

    # List accounts
    list_uc = ListMatrixAccountsUseCase(fake_matrix_account_repository)
    accounts = await list_uc.execute(user_id)
    assert len(accounts) == 1
    assert accounts[0].id == account_dto.id


@pytest.mark.asyncio
async def test_register_matrix_account_invalid_id_fails(
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    secret_cipher: SecretCipherPort,
) -> None:
    register_uc = RegisterMatrixAccountUseCase(fake_matrix_account_repository, secret_cipher)

    with pytest.raises(DomainError, match="Invalid Matrix User ID"):
        await register_uc.execute(
            RegisterMatrixAccountCommand(
                name="Bad User",
                matrix_user_id="invalid_user_without_server",
                user_id=uuid4(),
                password="password",
            )
        )


@pytest.mark.asyncio
async def test_create_and_process_webhook_with_matrix_account(
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_matrix_messenger: FakeMatrixMessenger,
    secret_cipher: SecretCipherPort,
) -> None:
    user_id = uuid4()

    # 1. Register a bot
    register_uc = RegisterMatrixAccountUseCase(fake_matrix_account_repository, secret_cipher)
    bot = await register_uc.execute(
        RegisterMatrixAccountCommand(
            name="Dedicated Bot",
            matrix_user_id="@dedicated:agent.tchap.gouv.fr",
            user_id=user_id,
            password="pass",
        )
    )

    # 2. Create webhook linked to this bot
    create_uc = CreateWebhookUseCase(
        webhook_repo=fake_webhook_repository,
        account_repo=fake_matrix_account_repository,
        public_base_url="http://gateway.test",
    )
    webhook = await create_uc.execute(
        CreateWebhookCommand(
            name="Prod Alerts",
            matrix_room_id="!prod:agent.tchap.gouv.fr",
            matrix_account_id=bot.id,
            user_id=user_id,
        )
    )

    assert webhook.name == "Prod Alerts"
    assert webhook.matrix_account_id == bot.id
    assert webhook.public_url == f"http://gateway.test/webhook/slack/{webhook.id}"

    # 3. Process alert through the public webhook
    client_manager = FakeMatrixClientManager(fake_matrix_messenger)
    process_uc = ProcessPublicWebhookUseCase(
        webhook_repo=fake_webhook_repository,
        client_manager=client_manager,
    )

    alert = AlertMessage(text="Database replication lag high", severity=AlertSeverity.WARNING)
    result = await process_uc.execute(SendPublicWebhookCommand(webhook_id=webhook.id, alert=alert))

    assert result.success is True
    assert result.room_id == "!prod:agent.tchap.gouv.fr"
    assert len(fake_matrix_messenger.sent_messages) == 1
    assert "Database replication lag high" in fake_matrix_messenger.sent_messages[0]["plain_body"]


@pytest.mark.asyncio
async def test_create_webhook_with_non_existent_matrix_account_fails(
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
) -> None:
    create_uc = CreateWebhookUseCase(
        webhook_repo=fake_webhook_repository,
        account_repo=fake_matrix_account_repository,
        public_base_url="http://gateway.test",
    )

    with pytest.raises(MatrixAccountNotFoundError):
        await create_uc.execute(
            CreateWebhookCommand(
                name="Orphan Webhook",
                matrix_room_id="!room:agent.tchap.gouv.fr",
                matrix_account_id=uuid4(),
                user_id=uuid4(),
            )
        )


@pytest.mark.asyncio
async def test_authenticate_api_key_use_case(fake_user_repository: FakeUserRepository) -> None:
    raw_key = "s2t_live_valid_api_key_secret_12345"
    hashed = hash_api_key(raw_key)

    user = User(
        email="admin@tchap.gouv.fr",
        api_key_hash=hashed,
        api_key_prefix="s2t_live_val...",
        is_admin=True,
    )
    await fake_user_repository.save(user)

    auth_uc = AuthenticateApiKeyUseCase(fake_user_repository)

    # Success
    auth_user = await auth_uc.execute(raw_key)
    assert auth_user.id == user.id
    assert auth_user.email == "admin@tchap.gouv.fr"

    # Bad key fails
    with pytest.raises(InvalidApiKeyError):
        await auth_uc.execute("s2t_live_invalid_key")


@pytest.mark.asyncio
async def test_delete_user_use_case_success(
    fake_user_repository: FakeUserRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_messenger: FakeMatrixMessenger,
) -> None:
    user = User(
        email="test_del@tchap.gouv.fr",
        api_key_hash="hash_123",
        api_key_prefix="prefix_123",
    )
    await fake_user_repository.save(user)

    bot = MatrixAccount(
        name="Bot",
        matrix_user_id="@bot:agent.tchap.gouv.fr",
        user_id=user.id,
    )
    await fake_matrix_account_repository.save(bot)

    wh = WebhookEndpoint(
        name="WH",
        matrix_room_id="!r:agent.tchap.gouv.fr",
        matrix_account_id=bot.id,
        user_id=user.id,
    )
    await fake_webhook_repository.save(wh)

    client_mgr = FakeMatrixClientManager(fake_matrix_messenger)
    use_case = DeleteUserUseCase(
        user_repo=fake_user_repository,
        account_repo=fake_matrix_account_repository,
        webhook_repo=fake_webhook_repository,
        client_manager=client_mgr,
    )

    result = await use_case.execute(user.id)
    assert result is True
    assert await fake_user_repository.get_by_id(user.id) is None
    assert await fake_matrix_account_repository.get_by_id(bot.id) is None
    assert await fake_webhook_repository.get_by_id(wh.id) is None
    assert bot.id in client_mgr.removed_clients


@pytest.mark.asyncio
async def test_delete_user_use_case_not_found(
    fake_user_repository: FakeUserRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_webhook_repository: FakeWebhookRepository,
) -> None:
    use_case = DeleteUserUseCase(
        user_repo=fake_user_repository,
        account_repo=fake_matrix_account_repository,
        webhook_repo=fake_webhook_repository,
    )
    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid4())


@pytest.mark.asyncio
async def test_delete_matrix_account_use_case(
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_messenger: FakeMatrixMessenger,
) -> None:
    owner_id = uuid4()
    other_user_id = uuid4()
    bot = MatrixAccount(
        name="Bot",
        matrix_user_id="@bot:agent.tchap.gouv.fr",
        user_id=owner_id,
    )
    await fake_matrix_account_repository.save(bot)

    wh = WebhookEndpoint(
        name="Hook",
        matrix_room_id="!room:agent.tchap.gouv.fr",
        matrix_account_id=bot.id,
        user_id=owner_id,
    )
    await fake_webhook_repository.save(wh)

    client_mgr = FakeMatrixClientManager(fake_matrix_messenger)
    use_case = DeleteMatrixAccountUseCase(
        account_repo=fake_matrix_account_repository,
        webhook_repo=fake_webhook_repository,
        client_manager=client_mgr,
    )

    # 1. Other non-admin user cannot delete
    with pytest.raises(MatrixAccountNotFoundError):
        await use_case.execute(bot.id, other_user_id, is_admin=False)

    # 2. Admin CAN delete other user's bot
    admin_id = uuid4()
    del_res = await use_case.execute(bot.id, admin_id, is_admin=True)
    assert del_res is True
    assert await fake_matrix_account_repository.get_by_id(bot.id) is None
    # Associated webhook was cascaded
    assert await fake_webhook_repository.get_by_id(wh.id) is None
    assert bot.id in client_mgr.removed_clients


@pytest.mark.asyncio
async def test_delete_webhook_use_case(
    fake_webhook_repository: FakeWebhookRepository,
) -> None:
    owner_id = uuid4()
    other_user_id = uuid4()
    wh = WebhookEndpoint(
        name="Hook",
        matrix_room_id="!room:agent.tchap.gouv.fr",
        matrix_account_id=uuid4(),
        user_id=owner_id,
    )
    await fake_webhook_repository.save(wh)

    use_case = DeleteWebhookUseCase(fake_webhook_repository)

    # 1. Other non-admin user cannot delete
    with pytest.raises(WebhookNotFoundError):
        await use_case.execute(wh.id, other_user_id, is_admin=False)

    # 2. Admin CAN delete other user's webhook
    del_res = await use_case.execute(wh.id, uuid4(), is_admin=True)
    assert del_res is True
    assert await fake_webhook_repository.get_by_id(wh.id) is None
