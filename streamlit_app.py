from collections import defaultdict
from enum import Enum

import requests
import streamlit as st


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
    data: list[Memo]
    url: str
    canceld_ids: set[int]

    def __init__(
        self, section: str, secret_key: str, url: str = "http://s.cympfh.cc/journal"
    ):
        self.url = f"{url}/{section}/{secret_key}"
        self.canceld_ids = set()

    def fetch(self):
        items = requests.get(self.url).json()
        self.data = [Memo.from_dict(item["data"]) for item in items]
        for memo in self.data:
            if memo.memo_type == MemoType.Cancel and memo.cancel_id is not None:
                self.canceld_ids.add(memo.cancel_id)

    def post(self, memo: Memo):
        return requests.post(self.url, json=memo.to_dict())

    def is_canceled(self, memo_id: int) -> bool:
        return memo_id in self.canceld_ids


def main():
    memo_client = MemoClient("shanghai2026", "prod")
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
                label="送金元", options=["神楽", "枚方"], selection_mode="single"
            )
            to_account = st.pills(
                label="送金元", options=["神楽", "枚方"], selection_mode="multi"
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

    paytotal = defaultdict(float)
    debt = defaultdict(float)
    for i, memo in reversed(list(enumerate(memo_client.data))):
        if memo_client.is_canceled(i):
            continue
        if memo.memo_type == MemoType.Payment:
            paytotal[memo.from_account] += memo.amount if memo.amount else 0
            accs = [acc.strip() for acc in memo.to_account.split(",")]
            for acc in accs:
                if memo.from_account != acc:
                    debt[acc] += memo.amount / len(accs) if memo.amount else 0

    if len(paytotal) > 0:
        with st.container(border=True):
            cols = st.columns(len(paytotal))
            for col, acc in zip(cols, paytotal.keys()):
                with col:
                    st.metric(
                        label=f"{acc} の支出",
                        value=f"{paytotal[acc]:.2f} 元",
                    )

            debt_diff = debt["神楽"] - debt["枚方"]
            if debt_diff == 0:
                st.success("神楽と枚方の債権は相殺されています。")
            elif debt_diff > 0:
                st.warning(f"神楽は枚方に対して {debt_diff} 元の債権があります。")
            else:
                st.warning(f"枚方は神楽に対して {-debt_diff} 元の債権があります。")

    st.subheader("履歴")
    history_exsists = False
    for i, memo in reversed(list(enumerate(memo_client.data))):
        if memo_client.is_canceled(i):
            continue
        history_exsists = True
        if memo.memo_type == MemoType.Payment:
            a, b, c, d, e = st.columns([1, 2, 3, 3, 3])
            with a:
                st.badge(f"ID: {i}", color="blue")
            with b:
                st.badge("支払", icon=":material/check:", color="green")
            with c:
                st.markdown(f"**{memo.from_account}** → **{memo.to_account}**")
            with d:
                st.markdown(f"**{memo.amount} 元**")
            with e:
                st.markdown(f"備考: {memo.note}" if memo.note else "備考: -")
        if memo.memo_type == MemoType.Note:
            a, b, c = st.columns([1, 2, 9])
            with a:
                st.badge(f"ID: {i}", color="blue")
            with b:
                st.badge("メモ", icon=":material/note:", color="orange")
            with c:
                st.markdown(f"**{memo.note}**")
    if history_exsists is False:
        st.info("履歴がありません")


if __name__ == "__main__":
    main()
