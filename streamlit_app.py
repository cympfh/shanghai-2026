import os
from collections import defaultdict
from enum import Enum

import qrcode
import requests
import streamlit as st


class User:
    @staticmethod
    def get(user_id: int) -> str:
        assert 0 <= user_id <= 1
        if user_id == 0:
            return "神楽"
        elif user_id == 1:
            return "枚方"
        raise

    @staticmethod
    def options() -> list[str]:
        return [User.get(user_id) for user_id in range(2)]

    @staticmethod
    def len() -> int:
        return 2


class Datetime:
    def __init__(self, raw_str: str):
        self.raw_str = raw_str  # ISO 8601 format (UTC)

    def show(self) -> str:
        """
        Show in YYYY-MM-DD HH:MM format
        """
        return self.raw_str.replace("T", " ")[:16]


class MemoType(Enum):
    Payment = "Payment"
    Cancel = "Cancel"
    Note = "Note"


class Memo:
    memo_id: int
    memo_type: MemoType
    from_account: str | None
    to_account: str | None
    amount: float | None
    cancel_id: int | None
    note: str | None

    def __init__(
        self,
        memo_id: int,
        memo_type: MemoType,
        from_account: str | None = None,
        to_account: str | None = None,
        amount: float | None = None,
        cancel_id: int | None = None,
        note: str | None = None,
    ) -> None:
        self.memo_id = memo_id
        self.memo_type = memo_type
        self.from_account = from_account
        self.to_account = to_account
        self.amount = amount
        self.cancel_id = cancel_id
        self.note = note

        # validation
        assert memo_id >= 0
        if memo_type == MemoType.Payment:
            if not from_account or not to_account:
                raise ValueError("Payment memo requires from_account and to_account")
        elif memo_type == MemoType.Cancel:
            if cancel_id is None:
                raise ValueError("Cancel memo requires cancel_id")
        elif memo_type == MemoType.Note:
            if note is None:
                raise ValueError("Note memo requires note")

    def to_dict(self):
        return {
            "memo_id": self.memo_id,
            "memo_type": self.memo_type.value,
            "from_account": self.from_account,
            "to_account": self.to_account,
            "amount": self.amount,
            "cancel_id": self.cancel_id,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, item):
        memo_type = MemoType(item["memo_type"])
        return Memo(
            memo_id=item["memo_id"],
            memo_type=memo_type,
            from_account=item.get("from_account"),
            to_account=item.get("to_account"),
            amount=item.get("amount"),
            cancel_id=item.get("cancel_id"),
            note=item.get("note"),
        )


class MemoClient:
    data: list[tuple[Memo, Datetime]]  # (Memo, timestamp)
    url: str
    canceld_ids: set[int]

    def __init__(
        self, section: str, secret_key: str, url: str = "http://s.cympfh.cc/journal"
    ):
        self.url = f"{url}/{section}/{secret_key}"
        self.canceld_ids = set()

    def fetch(self):
        for tail in [1000, 10000, 100000, 1000000]:
            items = requests.get(self.url, {"tail": tail}).json()
            self.data = [
                (Memo.from_dict(item["data"]), Datetime(item["timestamp"]))
                for item in items
            ]
            if len(self.data) == 0 or self.data[0][0].memo_id == 0:
                continue
            break
        self.canceld_ids = set()
        for memo, _ in self.data:
            if memo.memo_type == MemoType.Cancel and memo.cancel_id is not None:
                self.canceld_ids.add(memo.cancel_id)

    def post(self, memo: Memo):
        return requests.post(self.url, json=memo.to_dict())

    def __iter__(self):
        """Remove canceled memos"""
        for memo, timestamp in self.data:
            if (
                memo.memo_id not in self.canceld_ids
                and memo.memo_type != MemoType.Cancel
            ):
                yield memo, timestamp

    def history(self, reverse: bool = False) -> list[tuple[Memo, Datetime]]:
        ls = list(self.__iter__())
        if reverse:
            ls = list(reversed(ls))
        return ls

    def new_memo_id(self) -> int:
        if len(self.data) == 0:
            return 0
        return self.data[-1][0].memo_id + 1


def main():
    secret_key = os.environ.get("SHANGHAI_SECRET_KEY", "testkey")
    memo_client = MemoClient("shanghai2026", secret_key)
    memo_client.fetch()

    with st.container(border=True):
        ty = st.pills(
            label="種別",
            options=["支払", "メモ"],
            selection_mode="single",
        )
        if ty == "支払":
            from_account = st.pills(
                label="送金元", options=User.options(), selection_mode="single"
            )
            to_account = st.pills(
                label="送金元", options=User.options(), selection_mode="multi"
            )
            amount = st.number_input("金額 (元)", min_value=0.0, value=0.0, step=0.5)
            if from_account:
                if len(to_account) == 0:
                    st.info(f"{from_account} → ? : {amount} 元")
                elif len(to_account) == 1:
                    st.info(f"{from_account} → {to_account[0]} : {amount} 元")
                else:
                    st.info(
                        f"{from_account} → {','.join(to_account)} : {amount} 元 (= {amount / len(to_account)} 元 x {len(to_account)})"
                    )
            note = st.text_input("備考", "")
            if from_account and to_account and amount > 0:
                if st.button("送信"):
                    memo = Memo(
                        memo_id=memo_client.new_memo_id(),
                        memo_type=MemoType.Payment,
                        from_account=from_account,
                        to_account=",".join(to_account),
                        amount=amount,
                        note=note if note else None,
                    )
                    memo_client.post(memo)
                    st.rerun()

        elif ty == "メモ":
            note = st.text_input("メモ", "")
            if note:
                if st.button("送信"):
                    memo = Memo(
                        memo_id=memo_client.new_memo_id(),
                        memo_type=MemoType.Note,
                        note=note,
                    )
                    memo_client.post(memo)
                    st.rerun()

    # Summary
    paytotal = defaultdict(float)
    debt = defaultdict(float)
    for memo, timestamp in memo_client.history(reverse=True):
        if memo.memo_type == MemoType.Payment and memo.to_account:
            paytotal[memo.from_account] += memo.amount if memo.amount else 0
            accs = [acc.strip() for acc in memo.to_account.split(",")]
            for acc in accs:
                if memo.from_account != acc:
                    debt[acc] += memo.amount / len(accs) if memo.amount else 0

    if len(paytotal) > 0:
        with st.container(border=True):
            cols = st.columns(User.len())
            for i in range(User.len()):
                with cols[i]:
                    acc = User.get(i)
                    st.metric(
                        label=f"{acc} の支出",
                        value=f"{paytotal[acc]:.2f} 元",
                    )

            debt_diff = debt[User.get(0)] - debt[User.get(1)]
            if debt_diff == 0:
                st.success(f"{User.get(0)}と{User.get(1)}の債務は相殺されています。")
            elif debt_diff > 0:
                st.warning(
                    f"{User.get(0)}は{User.get(1)}に対して {debt_diff} 元の債務があります。"
                )
            else:
                st.warning(
                    f"{User.get(1)}は{User.get(0)}に対して {-debt_diff} 元の債務があります。"
                )

    # Bill history
    st.subheader("履歴")

    def build_payment_container(memo: Memo, timestamp: Datetime, delete_button: bool):
        with st.container(border=True):
            st.markdown(
                f":blue-badge[ID: {memo.memo_id}] :green-badge[:material/check: 支払] :gray-badge[:material/event_available: {timestamp.show()}]"
            )
            st.metric(
                label=f"{memo.from_account} → {memo.to_account}",
                value=f"{memo.amount} 元",
            )
            if memo.note:
                st.info(f"Note: {memo.note}")
            if delete_button:
                if st.button(
                    ":material/delete: 削除", key=f"cancel_payment_{memo.memo_id}"
                ):
                    delete_dialog(memo, timestamp)

    def build_memo_container(memo: Memo, timestamp: Datetime, delete_button: bool):
        with st.container(border=True):
            st.markdown(
                f":blue-badge[ID: {memo.memo_id}] :orange-badge[:material/note: Note] :gray-badge[:material/event_available: {timestamp.show()}]"
            )
            st.info(f"Note: {memo.note}")
            if delete_button:
                if st.button(
                    ":material/delete: 削除", key=f"cancel_note_{memo.memo_id}"
                ):
                    delete_dialog(memo, timestamp)

    @st.dialog("削除の確認")
    def delete_dialog(memo: Memo, timestamp: Datetime):
        st.markdown("以下の内容を削除してもよろしいですか？")
        if memo.memo_type == MemoType.Payment:
            build_payment_container(memo, timestamp, delete_button=False)
        elif memo.memo_type == MemoType.Note:
            build_memo_container(memo, timestamp, delete_button=False)
        else:
            st.warning("この項目は削除できません")
        if st.button("OK"):
            memo_client.post(
                Memo(
                    memo_id=memo_client.new_memo_id(),
                    memo_type=MemoType.Cancel,
                    cancel_id=memo.memo_id,
                )
            )
            st.rerun()

    for memo, timestamp in memo_client.history(reverse=True):
        if memo.memo_type == MemoType.Payment:
            build_payment_container(memo, timestamp, delete_button=True)
        if memo.memo_type == MemoType.Note and memo.note:
            build_memo_container(memo, timestamp, delete_button=True)

    if len(memo_client.history()) == 0:
        st.info("履歴がありません")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data("http://s.cympfh.cc/shanghai/")
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save("qrcode.png")
    _left, mid, _right = st.columns(3)
    with mid:
        st.image(
            "qrcode.png",
            use_container_width=False,
        )

    with st.expander("開発者向け情報"):
        for memo, timestamp in reversed(memo_client.data):
            st.json(
                {
                    "memo": memo.to_dict(),
                    "timestamp": timestamp.raw_str,
                }
            )


if __name__ == "__main__":
    main()
