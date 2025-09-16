import streamlit as st
from supabase import create_client
from decimal import Decimal
from datetime import date

# --- Конфигурација ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_ANON_KEY"]
sb = create_client(URL, KEY)

st.set_page_config(page_title="Менаџер за муштерии и долгови", layout="wide")

# --- Helpers ---
def dec(x):
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def fmt_money(d: Decimal) -> str:
    if d == d.to_integral_value():
        return f"{int(d)} ден."
    return f"{d:.2f} ден."

# --- Customers ---
def fetch_customers(q: str = ""):
    q = (q or "").strip()
    if not q:
        res = sb.table("customers").select("*").order("created_at", desc=True).execute()
    else:
        res = sb.table("customers").select("*").ilike("name", f"%{q}%").execute()
    return res.data if res.data else []

def insert_customer(name, phone, note, initial_debt):
    return sb.table("customers").insert({
        "name": name,
        "phone": phone,
        "note": note,
        "initial_debt": float(initial_debt)   # <-- важно: float во JSON
    }).execute()

def update_customer(cid, name, phone, note, initial_debt):
    return sb.table("customers").update({
        "name": name,
        "phone": phone,
        "note": note,
        "initial_debt": float(initial_debt)   # <-- важно: float
    }).eq("id", cid).execute()

def delete_customer(cid):
    return sb.table("customers").delete().eq("id", cid).execute()

# --- Payments ---
def fetch_payments(customer_id):
    res = sb.table("payments").select("*").eq("customer_id", customer_id)\
            .order("pay_date", desc=True).execute()
    return res.data if res.data else []

def add_payment(customer_id, amount, pay_date, note):
    return sb.table("payments").insert({
        "customer_id": customer_id,
        "amount": float(amount),              # <-- важно: float
        "pay_date": str(pay_date),
        "note": note
    }).execute()

# --- UI ---
st.title("📒 Менаџер за муштерии и долгови")

menu = st.sidebar.radio("Менито:", ["Листа", "Додај муштерија"])

if menu == "Листа":
    q = st.text_input("🔍 Пребарај муштерии (име/телефон)")
    customers = fetch_customers(q)

    if not customers:
        st.info("❌ Нема пронајдени муштерии.")
    else:
        for c in customers:
            col1, col2, col3, col4 = st.columns([3,2,2,2])
            with col1:
                st.write(f"**{c['name']}**")
                st.caption(c.get("phone") or "")
            with col2:
                st.write("📌 Почетен долг:", fmt_money(dec(c.get("initial_debt") or 0)))
            with col3:
                pays = fetch_payments(c["id"])
                total = dec(c.get("initial_debt") or 0) + sum(dec(p["amount"]) for p in pays)
                st.write("💰 Преостанато:", fmt_money(total))
            with col4:
                if st.button("📂 Детали", key=f"det-{c['id']}"):
                    st.session_state["view_customer"] = c["id"]

elif menu == "Додај муштерија":
    st.subheader("➕ Нова муштерија")
    name = st.text_input("Име и презиме")
    phone = st.text_input("Телефон")
    note = st.text_area("Белешка")
    debt = st.number_input("Почетен долг", min_value=0.0, step=100.0)
    if st.button("✅ Додади"):
        insert_customer(name, phone, note, debt)  # праќаме float, НЕ Decimal
        st.success("✅ Муштеријата е додадена!")

# --- Детален приказ ---
if "view_customer" in st.session_state:
    cid = st.session_state["view_customer"]
    cust_res = sb.table("customers").select("*").eq("id", cid).execute()
    if not cust_res.data:
        st.warning("Муштеријата не постои.")
    else:
        cust = cust_res.data[0]
        st.header(f"📌 Детали: {cust['name']}")

        # Основни податоци
        with st.expander("Основни податоци", expanded=True):
            new_name = st.text_input("Име и презиме", value=cust["name"])
            new_phone = st.text_input("Телефон", value=cust.get("phone") or "")
            new_note = st.text_area("Белешка", value=cust.get("note") or "")
            new_debt = st.number_input("Почетен долг", value=float(cust.get("initial_debt") or 0))
            if st.button("💾 Зачувај промени"):
                update_customer(cid, new_name, new_phone, new_note, new_debt)  # float
                st.success("✅ Промените се зачувани!")

            if st.button("🗑️ Избриши муштерија"):
                delete_customer(cid)
                st.session_state.pop("view_customer")
                st.warning("❌ Муштеријата е избришана!")

        # Уплати / нов долг
        st.subheader("💵 Уплати / Нов долг")
        pay_date = st.date_input("Датум", value=date.today())
        amount = st.number_input("Износ (уплата=+, нов долг=-)", step=100.0, format="%.2f")
        note = st.text_input("Белешка (опц.)")
        if st.button("➕ Додај ставка"):
            add_payment(cid, amount, pay_date, note)  # float
            st.success("✅ Ставката е додадена!")

        # Историја
        pays = fetch_payments(cid)
        if pays:
            st.write("📜 Историја на уплати/долгови")
            for p in pays:
                st.write(f"{p['pay_date']} | {fmt_money(dec(p['amount']))} | {p.get('note') or ''}")
        else:
            st.info("Нема уплати/долгови за овој клиент.")
