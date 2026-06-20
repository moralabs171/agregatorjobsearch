"""Тесты слоя хранения: подписки, дедупликация, дедуп уведомлений."""
from __future__ import annotations

import pytest

from storage import Storage


@pytest.fixture()
def store(tmp_path) -> Storage:
    return Storage(str(tmp_path / "test.db"))


def test_add_subscription_returns_created_flag(store: Storage) -> None:
    sub_id, created = store.add_subscription(1, 1, "Informatik", "")
    assert created is True
    assert sub_id > 0


def test_add_subscription_is_idempotent(store: Storage) -> None:
    first_id, first_created = store.add_subscription(1, 1, "Informatik", "")
    dup_id, dup_created = store.add_subscription(1, 1, "Informatik", "")

    assert first_created is True
    assert dup_created is False
    assert dup_id == first_id
    assert len(store.all_subscriptions()) == 1


def test_different_params_create_separate_subscriptions(store: Storage) -> None:
    store.add_subscription(1, 1, "Informatik", "")
    store.add_subscription(1, 1, "Informatik", "vz")  # другая занятость
    store.add_subscription(1, 4, "Informatik", "")  # другой тип
    store.add_subscription(2, 1, "Informatik", "")  # другой пользователь

    assert len(store.all_subscriptions()) == 4


def test_list_subscriptions_is_chat_scoped_and_ordered(store: Storage) -> None:
    a, _ = store.add_subscription(1, 1, "A", "")
    b, _ = store.add_subscription(1, 1, "B", "")
    store.add_subscription(2, 1, "C", "")

    subs = store.list_subscriptions(1)

    assert [s.id for s in subs] == [a, b]
    assert all(s.chat_id == 1 for s in subs)


def test_remove_subscription(store: Storage) -> None:
    sub_id, _ = store.add_subscription(1, 1, "Informatik", "")

    assert store.remove_subscription(1, sub_id) is True
    assert store.remove_subscription(1, sub_id) is False  # уже удалена
    assert store.list_subscriptions(1) == []


def test_remove_subscription_is_chat_scoped(store: Storage) -> None:
    sub_id, _ = store.add_subscription(1, 1, "Informatik", "")

    # чужой пользователь не может удалить чужую подписку
    assert store.remove_subscription(999, sub_id) is False
    assert len(store.list_subscriptions(1)) == 1


def test_seen_dedup_flow(store: Storage) -> None:
    sub_id, _ = store.add_subscription(1, 1, "Informatik", "")

    new = store.filter_new_refnrs(sub_id, ["r1", "r2", "r3"])
    assert new == {"r1", "r2", "r3"}

    store.mark_seen(sub_id, ["r1", "r2"])
    new_after = store.filter_new_refnrs(sub_id, ["r1", "r2", "r3"])
    assert new_after == {"r3"}


def test_mark_seen_is_idempotent(store: Storage) -> None:
    sub_id, _ = store.add_subscription(1, 1, "Informatik", "")
    store.mark_seen(sub_id, ["r1"])
    store.mark_seen(sub_id, ["r1"])  # повтор не должен падать

    assert store.filter_new_refnrs(sub_id, ["r1"]) == set()


def test_filter_new_refnrs_empty_input(store: Storage) -> None:
    sub_id, _ = store.add_subscription(1, 1, "Informatik", "")
    assert store.filter_new_refnrs(sub_id, []) == set()
