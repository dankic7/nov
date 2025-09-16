# -*- coding: utf-8 -*-
"""
Муштерии & Долгови – Tkinter + Supabase (v2)
- Нема локален JSON
- CRUD кон Supabase: customers / accounts / payments
- Export TXT (година), Збирно, Batch (по година)
"""

import os
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ==== Supabase ====
from supabase import create_client

# ако не користиш streamlit.secrets, можеш и преку env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# ако користиш .streamlit/secrets.toml, одкоментирај:
try:
    import streamlit as st  # само за читање secrets
    SUPABASE_URL = SUPABASE_URL or st.secrets["SUPABASE_URL"]
    SUPABASE_ANON_KEY = SUPABASE_ANON_KEY or st.secrets["SUPABASE_ANON_KEY"]
except Exception:
    pass

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Недостига SUPABASE_URL / SUPABASE_ANON_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ------------------------- Utility -------------------------
def money(val):
    try:
        d = Decimal(str(val)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        d = Decimal("0.00")
    return d

def today_iso():
    return date.today().isoformat()

def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None

# ------------------------- DB LAYER -------------------------
def db_list_customers(search=""):
    search = (search or "").strip()
    if not search:
        res = sb.table("customers").select("*").order("created_at", desc=True).execute()
    else:
        # пребарување во име/телефон
        res = (
            sb.table("customers")
              .select("*")
              .or_(f"name.ilike.%{search}%,phone.ilike.%{search}%")
              .order("created_at", desc=True)
              .execute()
        )
    return res.data or []

def db_get_customer(customer_id):
    res = sb.table("customers").select("*").eq("id", customer_id).limit(1).execute()
    return (res.data or [None])[0]

def db_insert_customer(name, phone, notes):
    res = sb.table("customers").insert({
        "name": name, "phone": phone, "notes": notes
    }).execute()
    return (res.data or [None])[0]

def db_update_customer(customer_id, name, phone, notes):
    sb.table("customers").update({
        "name": name, "phone": phone, "notes": notes
    }).eq("id", customer_id).execute()

def db_delete_customer(customer_id):
    sb.table("customers").delete().eq("id", customer_id).execute()

def db_get_initial_debt(customer_id, year):
    r = sb.table("accounts").select("initial_debt").eq("customer_id", customer_id).eq("year", year).execute()
    if r.data:
        return money(r.data[0].get("initial_debt", 0))
    return money(0)

def db_set_initial_debt(customer_id, year, value: Decimal):
    # upsert
    sb.table("accounts").upsert({
        "customer_id": customer_id,
        "year": str(year),
        "initial_debt": float(value)
    }, on_conflict="customer_id,year").execute()

def db_list_years(customer_id):
    r = sb.table("accounts").select("year").eq("customer_id", customer_id).execute()
    ys = sorted({row["year"] for row in (r.data or [])})
    # додади соседни за удобност
    cur = date.today().year
    for add in (-1, 0, 1):
        ys.append(str(cur + add))
    return sorted(set(ys))

def db_list_payments(customer_id, year):
    r = (
        sb.table("payments")
          .select("*")
          .eq("customer_id", customer_id)
          .eq("year", str(year))
          .order("pay_date", desc=False)
          .execute()
    )
    return r.data or []

def db_add_payment(customer_id, year, pay_date, amount: Decimal, note: str):
    sb.table("payments").insert({
        "customer_id": customer_id,
        "year": str(year),
        "pay_date": str(pay_date),
        "amount": float(amount),
        "note": note
    }).execute()

def db_update_payment(payment_id, pay_date, amount: Decimal, note):
    sb.table("payments").update({
        "pay_date": str(pay_date),
        "amount": float(amount),
        "note": note
    }).eq("id", payment_id).execute()

def db_delete_payment(payment_id):
    sb.table("payments").delete().eq("id", payment_id).execute()

# баланси:
def calc_year_balance(customer_id, year):
    init = db_get_initial_debt(customer_id, year)
    pays = db_list_payments(customer_id, year)
    total = sum(money(p["amount"]) for p in pays)
    return init - total

def calc_total_balance(customer_id):
    # сите години од accounts
    r = sb.table("accounts").select("year,initial_debt").eq("customer_id", customer_id).execute()
    total = Decimal("0.00")
    for row in (r.data or []):
        y = row["year"]
        total += calc_year_balance(customer_id, y)
    return total


# ------------------------- Dialogs -------------------------
class CustomerDialog(tk.Toplevel):
    def __init__(self, master, title="Нова муштерија", name="", phone="", notes=""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        pad = {"padx": 8, "pady": 6}

        tk.Label(self, text="Име и презиме:", font=("Segoe UI", 13)).grid(row=0, column=0, sticky="e", **pad)
        self.ent_name = tk.Entry(self, width=42, font=("Segoe UI", 14))
        self.ent_name.insert(0, name)
        self.ent_name.grid(row=0, column=1, **pad)

        tk.Label(self, text="Телефон (опц.):", font=("Segoe UI", 13)).grid(row=1, column=0, sticky="e", **pad)
        self.ent_phone = tk.Entry(self, width=42, font=("Segoe UI", 14))
        self.ent_phone.insert(0, phone)
        self.ent_phone.grid(row=1, column=1, **pad)

        tk.Label(self, text="Белешка (опц.):", font=("Segoe UI", 13)).grid(row=2, column=0, sticky="ne", **pad)
        self.txt_notes = tk.Text(self, width=42, height=4, font=("Segoe UI", 14))
        self.txt_notes.insert("1.0", notes)
        self.txt_notes.grid(row=2, column=1, **pad)

        btns = tk.Frame(self)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", **pad)
        ttk.Button(btns, text="Откажи", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="Зачувај", command=self.on_save).pack(side="right")
        self.ent_name.focus_set()

    def on_save(self):
        name = self.ent_name.get().strip()
        phone = self.ent_phone.get().strip()
        notes = self.txt_notes.get("1.0", "end").strip()
        if not name:
            messagebox.showwarning("Проверка", "Внесете име и презиме.")
            return
        self.result = {"name": name, "phone": phone, "notes": notes}
        self.destroy()


class PaymentDialog(tk.Toplevel):
    def __init__(self, master, title="Нова ставка (уплата/долг)", date_str=None, amount="", note=""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        pad = {"padx": 8, "pady": 6}
        tk.Label(self, text="Датум (YYYY-MM-DD или DD.MM.YYYY):", font=("Segoe UI", 13)).grid(row=0, column=0, sticky="e", **pad)
        self.ent_date = tk.Entry(self, width=22, font=("Segoe UI", 14))
        self.ent_date.insert(0, date_str or today_iso())
        self.ent_date.grid(row=0, column=1, **pad)

        tk.Label(self, text="Износ (+уплата / -нов долг):", font=("Segoe UI", 13)).grid(row=1, column=0, sticky="e", **pad)
        self.ent_amount = tk.Entry(self, width=22, font=("Segoe UI", 14))
        self.ent_amount.insert(0, str(amount))
        self.ent_amount.grid(row=1, column=1, **pad)

        tk.Label(self, text="Белешка (опц.):", font=("Segoe UI", 13)).grid(row=2, column=0, sticky="e", **pad)
        self.ent_note = tk.Entry(self, width=34, font=("Segoe UI", 14))
        self.ent_note.insert(0, note)
        self.ent_note.grid(row=2, column=1, **pad)

        btns = tk.Frame(self)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", **pad)
        ttk.Button(btns, text="Откажи", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="Зачувај", command=self.on_save).pack(side="right")
        self.ent_date.focus_set()

    def on_save(self):
        ds = parse_date(self.ent_date.get())
        if not ds:
            messagebox.showwarning("Проверка", "Внесете валиден датум.")
            return
        try:
            amt = money(self.ent_amount.get())  # може и негативно
        except Exception:
            messagebox.showwarning("Проверка", "Внесете валиден износ (пример 123.45).")
            return
        note = self.ent_note.get().strip()
        self.result = {"pay_date": ds, "amount": float(amt), "note": note}
        self.destroy()


# ------------------------- Detail Window -------------------------
class CustomerDetail(tk.Toplevel):
    def __init__(self, master, customer_id):
        super().__init__(master)
        self.title("Детали за муштерија")
        self.geometry("980x640")
        self.customer_id = customer_id
        self.cust = db_get_customer(customer_id)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        pad = {"padx": 8, "pady": 6}

        # Header
        info = tk.Frame(self); info.grid(row=0, column=0, sticky="ew", **pad)
        info.columnconfigure(1, weight=1)
        tk.Label(info, text="Име и презиме:", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(info, text=self.cust.get("name",""), font=("Segoe UI", 14)).grid(row=0, column=1, sticky="w")
        tk.Label(info, text="Телефон:", font=("Segoe UI", 13, "bold")).grid(row=1, column=0, sticky="w")
        tk.Label(info, text=self.cust.get("phone","-"), font=("Segoe UI", 14)).grid(row=1, column=1, sticky="w")

        # Year & initial debt
        ybox = ttk.LabelFrame(self, text="Година & Почетен долг")
        ybox.grid(row=1, column=0, sticky="ew", **pad)
        for i in range(10): ybox.columnconfigure(i, weight=1)

        tk.Label(ybox, text="Година:", font=("Segoe UI", 13)).grid(row=0, column=0, sticky="e", **pad)
        self.cmb_year = ttk.Combobox(ybox, values=db_list_years(self.customer_id), width=10, state="readonly")
        self.cmb_year.grid(row=0, column=1, **pad)
        self.cmb_year.set(str(date.today().year))

        ttk.Button(ybox, text="Избери година", command=self.refresh_year_ui)\
            .grid(row=0, column=2, **pad)

        tk.Label(ybox, text="Почетен долг:", font=("Segoe UI", 13)).grid(row=0, column=3, sticky="e", **pad)
        self.ent_initial = tk.Entry(ybox, width=16, font=("Segoe UI", 14))
        self.ent_initial.grid(row=0, column=4, **pad)
        ttk.Button(ybox, text="Зачувај долг", command=self.on_save_initial)\
            .grid(row=0, column=5, **pad)

        self.btn_export_year   = ttk.Button(ybox, text="Извези TXT (година)", command=self.on_export_txt_year);   self.btn_export_year.grid(row=0, column=6, **pad)
        self.btn_export_zbirno = ttk.Button(ybox, text="Извези TXT (збирно)", command=self.on_export_txt_all_years_one); self.btn_export_zbirno.grid(row=0, column=7, **pad)
        self.btn_export_batch  = ttk.Button(ybox, text="Извези TXT (batch/години)", command=self.on_export_txt_each_year_file); self.btn_export_batch.grid(row=0, column=8, **pad)

        self.lbl_balance = tk.Label(ybox, text="Салдо: 0.00", font=("Segoe UI", 14, "bold"))
        self.lbl_balance.grid(row=1, column=0, columnspan=10, sticky="w", **pad)

        # Payments
        box = ttk.LabelFrame(self, text="Уплати за избраната година")
        box.grid(row=2, column=0, sticky="nsew", **pad)
        box.rowconfigure(0, weight=1); box.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(box, columns=("id","date","amount","note"), show="headings", height=12)
        self.tree.heading("date", text="Датум")
        self.tree.heading("amount", text="Износ")
        self.tree.heading("note", text="Белешка")
        self.tree.column("id", width=0, stretch=False)  # скриено id
        self.tree.column("date", width=140, anchor="center")
        self.tree.column("amount", width=160, anchor="e")
        self.tree.column("note", width=520, anchor="w")

        yscroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns")

        btns = tk.Frame(self); btns.grid(row=3, column=0, sticky="e", **pad)
        ttk.Button(btns, text="Додади ставка",  command=self.on_add_payment).pack(side="left", padx=4)
        ttk.Button(btns, text="Уреди ставка",   command=self.on_edit_payment).pack(side="left", padx=4)
        ttk.Button(btns, text="Избриши ставка", command=self.on_delete_payment).pack(side="left", padx=4)

        self.refresh_year_ui()

    # ----- Year/UI -----
    def refresh_year_ui(self):
        y = self.cmb_year.get().strip()
        init = db_get_initial_debt(self.customer_id, y)
        self.ent_initial.delete(0, "end"); self.ent_initial.insert(0, f"{init:.2f}")

        # табела
        for i in self.tree.get_children(): self.tree.delete(i)
        for p in db_list_payments(self.customer_id, y):
            self.tree.insert("", "end", values=(p["id"], p["pay_date"], f"{money(p['amount']):.2f}", p.get("note","")))

        bal = calc_year_balance(self.customer_id, y)
        self.lbl_balance.config(text=f"Салдо за {y}: {bal:.2f}")

        # извести parent да освежи
        if hasattr(self.master, "refresh_list"): self.master.refresh_list()

    def on_save_initial(self):
        y = self.cmb_year.get().strip()
        try:
            val = money(self.ent_initial.get())
            if val < 0: raise ValueError
        except Exception:
            messagebox.showwarning("Проверка", "Внесете валиден износ.")
            return
        db_set_initial_debt(self.customer_id, y, val)
        messagebox.showinfo("Снимено", "Почетниот долг е сочуван.")
        self.refresh_year_ui()

    # ----- Payments -----
    def _selected_payment_id(self):
        sel = self.tree.selection()
        if not sel: return None
        return self.tree.item(sel[0])["values"][0]  # id во првата (скриена) колона

    def on_add_payment(self):
        dlg = PaymentDialog(self, title="Нова ставка (уплата/долг)")
        self.wait_window(dlg)
        if not dlg.result: return
        y = self.cmb_year.get().strip()
        db_add_payment(self.customer_id, y, dlg.result["pay_date"], money(dlg.result["amount"]), dlg.result["note"])
        self.refresh_year_ui()

    def on_edit_payment(self):
        pid = self._selected_payment_id()
        if not pid:
            messagebox.showwarning("Избор", "Изберете ставка.")
            return
        # земи тековни вредности од редот
        vals = self.tree.item(self.tree.selection()[0])["values"]
        dlg = PaymentDialog(self, title="Уреди ставка", date_str=vals[1], amount=vals[2], note=vals[3])
        self.wait_window(dlg)
        if not dlg.result: return
        db_update_payment(pid, dlg.result["pay_date"], money(dlg.result["amount"]), dlg.result["note"])
        self.refresh_year_ui()

    def on_delete_payment(self):
        pid = self._selected_payment_id()
        if not pid:
            messagebox.showwarning("Избор", "Изберете ставка.")
            return
        if not messagebox.askyesno("Потврда", "Да ја избришам ставката?"): return
        db_delete_payment(pid); self.refresh_year_ui()

    # ----- Export helpers -----
    def _compose_year_lines(self, year):
        init = db_get_initial_debt(self.customer_id, year)
        pays = db_list_payments(self.customer_id, year)
        pays_sorted = sorted(pays, key=lambda p: p["pay_date"])
        total_paid = sum(money(p["amount"]) for p in pays_sorted)
        balance = init - total_paid

        lines = []
        lines.append("===========================================")
        lines.append(f"   ИЗВЕШТАЈ ЗА МУШТЕРИЈА – ГОДИНА: {year}")
        lines.append("===========================================")
        lines.append(f"Датум на извештај: {today_iso()}")
        lines.append(f"Муштерија : {self.cust.get('name','')}")
        lines.append(f"Телефон   : {self.cust.get('phone','-')}")
        lines.append("")
        lines.append(f"Почетен долг: {init:.2f} ден.")
        lines.append("-------------------------------------------")
        lines.append("УПЛАТИ:")
        if pays_sorted:
            for i, p in enumerate(pays_sorted, 1):
                dt = p["pay_date"]; amt = money(p["amount"]); note = p.get("note","")
                lines.append(f"{i:02d}. {dt}  |  {amt:.2f} ден.  |  {note}")
        else:
            lines.append("Нема евидентирани уплати за оваа година.")
        lines.append("-------------------------------------------")
        lines.append(f"Вкупно уплатено: {total_paid:.2f} ден.")
        lines.append(f"Преостанато салдо: {balance:.2f} ден.")
        lines.append("")
        return lines, total_paid, balance, init

    def on_export_txt_year(self):
        y = self.cmb_year.get().strip()
        if not y: return
        lines, *_ = self._compose_year_lines(y)
        txt = "\n".join(lines)
        suggested = f"Izvestaj_{self.cust.get('name','').replace(' ','_')}_{y}.txt"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=suggested,
                                            filetypes=[("Text file","*.txt")], title="Сними TXT (година)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f: f.write(txt)
        messagebox.showinfo("Успех", f"Снимено:\n{path}")

    def on_export_txt_all_years_one(self):
        # сите години што има записи во accounts
        r = sb.table("accounts").select("year,initial_debt").eq("customer_id", self.customer_id).execute()
        years = sorted({row["year"] for row in (r.data or [])})
        if not years:
            messagebox.showwarning("Инфо", "Нема внесени години.")
            return
        all_lines = []
        gi = gp = gb = Decimal("0.00")

        header = [
            "============================================================",
            "         ЗБИРЕН ИЗВЕШТАЈ ЗА МУШТЕРИЈА (сите години)",
            "============================================================",
            f"Датум на извештај: {today_iso()}",
            f"Муштерија : {self.cust.get('name','')}",
            f"Телефон   : {self.cust.get('phone','-')}",
            ""
        ]
        all_lines.extend(header)

        for y in years:
            lines, paid, bal, init = self._compose_year_lines(y)
            all_lines.extend(lines)
            gi += money(init); gp += money(paid); gb += money(bal)

        all_lines += [
            "============================================================",
            "                  ВКУПНИ ЗБИРНИ ВРЕДНОСТИ",
            "============================================================",
            f"Вкупно почетни долгови (сите години): {gi:.2f} ден.",
            f"Вкупно уплатено (сите години):        {gp:.2f} ден.",
            f"Збирно преостанато салдо:             {gb:.2f} ден.",
            "============================================================",
            ""
        ]
        txt = "\n".join(all_lines)
        suggested = f"Izvestaj_ZBIRNO_{self.cust.get('name','').replace(' ','_')}.txt"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=suggested,
                                            filetypes=[("Text file","*.txt")], title="Сними TXT (збирно)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f: f.write(txt)
        messagebox.showinfo("Успех", f"Снимено:\n{path}")

    def on_export_txt_each_year_file(self):
        r = sb.table("accounts").select("year").eq("customer_id", self.customer_id).execute()
        years = sorted({row["year"] for row in (r.data or [])})
        if not years:
            messagebox.showwarning("Инфо", "Нема внесени години.")
            return
        dirname = filedialog.askdirectory(title="Одбери папка за Batch TXT (по година)")
        if not dirname: return
        count = 0
        for y in years:
            lines, *_ = self._compose_year_lines(y)
            path = os.path.join(dirname, f"Izvestaj_{self.cust.get('name','').replace(' ','_')}_{y}.txt")
            with open(path, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            count += 1
        messagebox.showinfo("Готово", f"Batch export заврши. Креирани фајлови: {count}")


# ------------------------- Main Window -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Муштерии & Долгови – Supabase")
        self.geometry("980x700")

        # UI стил
        style = ttk.Style()
        try:
            style.configure(".", font=("Segoe UI", 13))
            style.configure("Treeview.Heading", font=("Segoe UI", 13, "bold"))
            style.configure("Treeview", rowheight=28)
        except Exception:
            pass

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = tk.Frame(self); top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        tk.Label(top, text="Пребарај:", font=("Segoe UI", 13)).pack(side="left")
        self.ent_search = tk.Entry(top, width=44, font=("Segoe UI", 14))
        self.ent_search.pack(side="left", padx=8)
        self.ent_search.bind("<KeyRelease>", lambda e: self.refresh_list())
        ttk.Button(top, text="Избриши филтер", command=self.clear_search).pack(side="left", padx=4)

        box = ttk.LabelFrame(self, text="Листа на муштерии (двоклик за детали)")
        box.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)
        box.rowconfigure(0, weight=1); box.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(box, columns=("id","name","phone","balance"), show="headings")
        self.tree.heading("name", text="Име и презиме")
        self.tree.heading("phone", text="Телефон")
        self.tree.heading("balance", text="Вкупно салдо")
        self.tree.column("id", width=0, stretch=False)
        self.tree.column("name", width=380, anchor="w")
        self.tree.column("phone", width=180, anchor="center")
        self.tree.column("balance", width=180, anchor="e")

        yscroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.on_double_click)

        btns = tk.Frame(self); btns.grid(row=3, column=0, sticky="e", padx=8, pady=6)
        ttk.Button(btns, text="Додади муштерија", command=self.on_add).pack(side="left", padx=4)
        ttk.Button(btns, text="Уреди муштерија", command=self.on_edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Избриши муштерија", command=self.on_delete).pack(side="left", padx=4)

        self.refresh_list()

    # ----- list helpers -----
    def refresh_list(self):
        query = self.ent_search.get().strip()
        for i in self.tree.get_children(): self.tree.delete(i)
        self._rows_cache = []  # (id, name, phone)
        for c in db_list_customers(query):
            bal = calc_total_balance(c["id"])
            self.tree.insert("", "end", values=(c["id"], c["name"], c.get("phone",""), f"{bal:.2f}"))
            self._rows_cache.append((c["id"], c["name"], c.get("phone","")))

    def clear_search(self):
        self.ent_search.delete(0, "end")
        self.refresh_list()

    def _selected_customer_id(self):
        sel = self.tree.selection()
        if not sel: return None
        return self.tree.item(sel[0])["values"][0]

    # ----- actions -----
    def on_add(self):
        dlg = CustomerDialog(self, title="Нова муштерија")
        self.wait_window(dlg)
        if not dlg.result: return
        db_insert_customer(dlg.result["name"], dlg.result["phone"], dlg.result["notes"])
        self.refresh_list()

    def on_edit(self):
        cid = self._selected_customer_id()
        if not cid:
            messagebox.showwarning("Избор", "Изберете муштерија.")
            return
        c = db_get_customer(cid)
        dlg = CustomerDialog(self, title="Уреди муштерија",
                             name=c.get("name",""), phone=c.get("phone",""), notes=c.get("notes",""))
        self.wait_window(dlg)
        if not dlg.result: return
        db_update_customer(cid, dlg.result["name"], dlg.result["phone"], dlg.result["notes"])
        self.refresh_list()

    def on_delete(self):
        cid = self._selected_customer_id()
        if not cid:
            messagebox.showwarning("Избор", "Изберете муштерија.")
            return
        c = db_get_customer(cid)
        if not messagebox.askyesno("Потврда", f"Избриши ја муштеријата „{c.get('name','')}“?"): return
        db_delete_customer(cid)
        self.refresh_list()

    def on_double_click(self, _event):
        cid = self._selected_customer_id()
        if not cid: return
        CustomerDetail(self, cid)


if __name__ == "__main__":
    App().mainloop()
