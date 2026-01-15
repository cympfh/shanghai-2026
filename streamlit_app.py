import os
from collections import defaultdict
from enum import Enum

import qrcode
import requests
import streamlit as st


class User:
    @staticmethod
    def get(i: int) -> str:
        assert 0 <= i <= 1
        if i == 0:
            return "神楽"
        elif i == 1:
            return "枚方"
        raise

    @staticmethod
    def options() -> list[str]:
        return [User.get(i) for i in range(2)]

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
    memo_type: MemoType
    from_account: str | None
    to_account: str | None
    amount: float | None
    cancel_id: int | None
    note: str | None

    def __init__(
        self,
        memo_type: MemoType,
        from_account: str | None = None,
        to_account: str | None = None,
        amount: float | None = None,
        cancel_id: int | None = None,
        note: str | None = None,
    ) -> None:
        self.memo_type = memo_type
        self.from_account = from_account
        self.to_account = to_account
        self.amount = amount
        self.cancel_id = cancel_id
        self.note = note

        # validation
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
            memo_type=memo_type,
            from_account=item.get("from_account"),
            to_account=item.get("to_account"),
            amount=item.get("amount"),
            cancel_id=item.get("cancel_id"),
            note=item.get("note"),
        )


class MemoClient:
    data: list[tuple[int, Memo, Datetime]]  # (id, Memo, timestamp)
    url: str
    canceld_ids: set[int]

    def __init__(
        self, section: str, secret_key: str, url: str = "http://s.cympfh.cc/journal"
    ):
        self.url = f"{url}/{section}/{secret_key}"
        self.canceld_ids = set()

    def fetch(self):
        items = requests.get(self.url).json()
        self.data = [
            (id, Memo.from_dict(item["data"]), Datetime(item["timestamp"]))
            for id, item in enumerate(items)
        ]
        self.canceld_ids = set()
        for _, memo, _ in self.data:
            if memo.memo_type == MemoType.Cancel and memo.cancel_id is not None:
                self.canceld_ids.add(memo.cancel_id)

    def post(self, memo: Memo):
        return requests.post(self.url, json=memo.to_dict())

    def is_canceled(self, memo_id: int) -> bool:
        return memo_id in self.canceld_ids

    def __iter__(self):
        """Remove canceled memos"""
        for i, memo, timestamp in self.data:
            if not self.is_canceled(i):
                yield i, memo, timestamp


def main():
    secret_key = os.environ.get("SHANGHAI_SECRET_KEY", "prod")
    memo_client = MemoClient("shanghai2026", secret_key)
    memo_client.fetch()

    with st.container(border=True):
        ty = st.pills(
            label="種別",
            options=[
                "支払",
                "取消",
                "メモ",
            ],
            selection_mode="single",
        )
        if ty == "支払":
            from_account = st.pills(
                label="送金元", options=User.options(), selection_mode="single"
            )
            to_account = st.pills(
                label="送金元", options=User.options(), selection_mode="multi"
            )
            amount = st.number_input("金額 (元)", min_value=0, value=0)
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
                        memo_type=MemoType.Payment,
                        from_account=from_account,
                        to_account=",".join(to_account),
                        amount=amount,
                        note=note if note else None,
                    )
                    memo_client.post(memo)
                    st.rerun()

        elif ty == "取消":
            cancel_id = st.number_input("取消する支払のID", min_value=-1, value=-1)
            note = st.text_input("備考", "")
            if cancel_id >= 0:
                if st.button("送信"):
                    memo = Memo(
                        memo_type=MemoType.Cancel,
                        cancel_id=cancel_id,
                        note=note if note else None,
                    )
                    memo_client.post(memo)
                    st.rerun()

        elif ty == "メモ":
            note = st.text_input("メモ", "")
            if note:
                if st.button("送信"):
                    memo = Memo(
                        memo_type=MemoType.Note,
                        note=note,
                    )
                    memo_client.post(memo)
                    st.rerun()

    # Summary
    paytotal = defaultdict(float)
    debt = defaultdict(float)
    for i, memo, timestamp in reversed(list(memo_client)):
        if memo.memo_type == MemoType.Payment:
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
                st.success(f"{User.get(0)}と{User.get(1)}の債権は相殺されています。")
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
    history = list(memo_client)
    for i, memo, timestamp in reversed(history):
        if memo.memo_type == MemoType.Payment:
            with st.container(border=True):
                st.markdown(
                    f":blue-badge[ID: {i}] :green-badge[:material/check: 支払] :gray-badge[:material/event_available: {timestamp.show()}]"
                )
                st.metric(
                    label=f"{memo.from_account} → {memo.to_account}",
                    value=f"{memo.amount} 元",
                )
                if memo.note:
                    st.info(f"Note: {memo.note}")
        if memo.memo_type == MemoType.Note and memo.note:
            with st.container(border=True):
                st.markdown(
                    f":blue-badge[ID: {i}] :orange-badge[:material/note: Note] :gray-badge[:material/event_available: {timestamp.show()}]"
                )
                st.info(f"Note: {memo.note}")

    if len(history) == 0:
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


if __name__ == "__main__":
    main()
