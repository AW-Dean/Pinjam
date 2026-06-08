import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime
import pytz
import json

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="AWE Peminjaman Barang", layout="wide")

# --- KONEKSI MOTHERDUCK ---
@st.cache_resource
def get_connection():
    try:
        # Mengambil token dari Streamlit Secrets
        md_token = st.secrets["MOTHERDUCK_TOKEN"]
        # Koneksi ke root MotherDuck dulu agar aman
        return duckdb.connect(f"md:?motherduck_token={md_token}")
    except KeyError:
        st.error("❌ Secrets 'MOTHERDUCK_TOKEN' tidak ditemukan. Sila tambahkan di Settings > Secrets pada Streamlit Cloud.")
        st.stop()

# --- INISIALISASI DATABASE ---
def init_db(conn):
    # Dijalankan sekali untuk memastikan skema ada
    # Buat database dan tabel jika belum ada
    conn.execute("CREATE DATABASE IF NOT EXISTS AWE_DB")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS AWE_DB.seq_id")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS AWE_DB.peminjaman (
            id INTEGER PRIMARY KEY,
            barcode VARCHAR,
            tanggal_kedatangan DATE,
            nama_barang VARCHAR,
            berat_gr DOUBLE,
            status VARCHAR DEFAULT 'Dipinjam',
            waktu_pinjam TIMESTAMP,
            waktu_kembali TIMESTAMP
        )
    """)

    # --- QUERY MIGRASI SEMENTARA ---
    # Tambahkan warna_item jika belum ada
    try:
        conn.execute("ALTER TABLE AWE_DB.peminjaman ADD COLUMN warna_item VARCHAR")
    except:
        pass

    # Hapus kolom lama jika masih ada agar tidak membingungkan
    try:
        conn.execute("ALTER TABLE AWE_DB.peminjaman DROP COLUMN seri_item")
        conn.execute("ALTER TABLE AWE_DB.peminjaman DROP COLUMN jenis_item")
    except:
        pass

# --- UTILS ---
def get_wib_now():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def format_warna_display(json_str):
    try:
        data = json.loads(json_str)
        return " | ".join([f"{d['warna']}: {d['berat']}g" for d in data])
    except:
        return json_str

conn = get_connection()
init_db(conn)

st.title("📦 Sistem Manajemen Peminjaman (AWE_DB)")

tab1, tab2, tab3 = st.tabs(["📝 Form Peminjaman", "🔄 Pengembalian", "📊 Data Peminjaman"])

# Inisialisasi state untuk jumlah baris warna jika belum ada
if "rows_warna" not in st.session_state:
    st.session_state.rows_warna = 1

# --- TAB 1: FORM PEMINJAMAN ---
with tab1:
    st.subheader("Input Peminjaman Barang")
    
    # 1. Input Utama (Full Width/Satu Kontainer Penuh)
    barcode = st.text_input("Barcode Utama")
    nama_barang = st.text_input("Nama Barang")
    tgl_datang = st.date_input("Tanggal Kedatangan")

    st.write("---")
    
    # 2. Info diletakkan di atas rincian berat & warna
    st.info("Klik tombol 'Tambah Baris Warna' di bawah untuk menambah warna yang sama dengan berat berbeda.")

    # 3. Fragment untuk mencegah loading glitch pada seluruh halaman
    @st.fragment
    def input_warna_fragment():
        st.markdown("##### ⚖️ Rincian Warna & Berat")
        warna_with_berat = []
        total_berat = 0.0
        
        # Loop baris input
        for i in range(st.session_state.rows_warna):
            c1, c2 = st.columns([2, 2])
            with c1:
                w_val = st.selectbox(f"Warna {i+1}", ["Semu", "Putih", "PB", "Puth Kapas"], key=f"warna_sel_{i}")
            with c2:
                b_val = st.number_input(f"Berat {i+1} (gr)", min_value=0.0, step=1.0, format="%.2f", key=f"berat_in_{i}")
            
            warna_with_berat.append({"warna": w_val, "berat": b_val})
            total_berat += b_val

        # Kontrol Baris
        col_btn1, col_btn2, _ = st.columns([1, 1, 2])
        with col_btn1:
            if st.button("➕ Tambah Baris"):
                st.session_state.rows_warna += 1
                st.rerun()
        with col_btn2:
            if st.button("🗑️ Hapus Baris") and st.session_state.rows_warna > 1:
                st.session_state.rows_warna -= 1
                st.rerun()

        st.success(f"**Total Berat Gabungan:** {total_berat:.2f} gr")
        return warna_with_berat, total_berat

    # Panggil fragment
    warna_data, berat_total = input_warna_fragment()
    st.write("---")

    if st.button("Simpan Data Peminjaman", type="primary", use_container_width=True):
        if barcode and nama_barang and berat_total > 0:
            waktu_wib = get_wib_now()
            conn.execute("""
                INSERT INTO AWE_DB.peminjaman (id, barcode, tanggal_kedatangan, nama_barang, berat_gr, warna_item, waktu_pinjam)
                VALUES (nextval('AWE_DB.seq_id'), ?, ?, ?, ?, ?, ?)
            """, (barcode, tgl_datang, nama_barang, berat_total, json.dumps(warna_data), waktu_wib.replace(tzinfo=None)))
            
            # Reset baris ke 1 setelah simpan
            st.session_state.rows_warna = 1
            st.success(f"✅ Berhasil menginput data Barcode: {barcode}")
            st.rerun()
        else:
            st.error("❌ Barcode, Nama Barang, dan Berat Warna harus diisi dengan benar!")

# --- TAB 2: PENGEMBALIAN ---
with tab2:
    st.subheader("Form Pengembalian")
    
    # Mode cepat untuk memproses scan tanpa klik tombol tambahan
    mode_cepat = st.toggle("Mode Scan Cepat (Otomatis Setujui)", value=True)
    
    input_barcode_kembali = st.text_input(
        "Scan Barcode untuk Pengembalian", 
        placeholder="Arahkan scanner ke barcode...",
        key="input_barcode_ret"
    )
    
    if input_barcode_kembali:
        # Cari data yang statusnya masih 'Dipinjam'
        query = "SELECT id, nama_barang, warna_item, berat_gr, waktu_pinjam FROM AWE_DB.peminjaman WHERE barcode = ? AND status = 'Dipinjam'"
        data_kembali = conn.execute(query, (input_barcode_kembali,)).df()
        
        if not data_kembali.empty:
            if mode_cepat:
                # Langsung proses pengembalian tanpa menunggu klik tombol
                waktu_kembali = get_wib_now()
                conn.execute("""
                    UPDATE AWE_DB.peminjaman 
                    SET status = 'Kembali', waktu_kembali = ? 
                    WHERE barcode = ? AND status = 'Dipinjam'
                """, (waktu_kembali.replace(tzinfo=None), input_barcode_kembali))
                
                st.toast(f"✅ Barcode {input_barcode_kembali} Berhasil Kembali!", icon='📦')
                # Berikan delay sedikit agar operator bisa melihat feedback sebelum field dibersihkan
                st.info(f"Berhasil mengembalikan: {data_kembali.iloc[0]['nama_barang']}")
                if st.button("Siap untuk Scan Berikutnya"):
                    st.rerun()
            else:
                data_kembali['warna_item'] = data_kembali['warna_item'].apply(format_warna_display)
                st.write("Detail Barang yang Dipinjam:")
                st.dataframe(data_kembali, use_container_width=True, hide_index=True)
                
                if st.button("✅ Setujui Pengembalian", type="primary"):
                    waktu_kembali = get_wib_now()
                    conn.execute("""
                        UPDATE AWE_DB.peminjaman 
                        SET status = 'Kembali', waktu_kembali = ? 
                        WHERE barcode = ? AND status = 'Dipinjam'
                    """, (waktu_kembali.replace(tzinfo=None), input_barcode_kembali))
                    st.success(f"✅ Barcode {input_barcode_kembali} berhasil dikembalikan!")
                    st.rerun()
        else:
            st.warning("⚠️ Tidak ada item aktif yang dipinjam dengan barcode tersebut.")

# --- TAB 3: LIHAT DATA (EDIT & HAPUS) ---
with tab3:
    st.subheader("Daftar Riwayat Peminjaman")
    df = conn.execute("SELECT id, barcode, nama_barang, warna_item, berat_gr, status, waktu_pinjam, waktu_kembali FROM AWE_DB.peminjaman ORDER BY waktu_pinjam DESC").df()

    if not df.empty:
        # --- RINGKASAN DATA (CARDS) ---
        df_active = df[df['status'] == 'Dipinjam']
        total_items = len(df_active)
        total_weight = df_active['berat_gr'].sum()

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("📦 Total Barang Dipinjam", f"{total_items} Item")
        with col_m2:
            st.metric("⚖️ Total Berat Dipinjam", f"{total_weight:,.2f} gr")

        # --- BREAKDOWN BERAT PER NAMA BARANG ---
        if not df_active.empty:
            st.markdown("###### 📋 Rincian Berat Kumulatif per Nama Barang (Status: Dipinjam)")
            df_sum = df_active.groupby('nama_barang')['berat_gr'].sum().reset_index()
            df_sum.columns = ["Nama Barang", "Total Berat (gr)"]
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

        df_display = df.copy()
        df_display['warna_item'] = df_display['warna_item'].apply(format_warna_display)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("Aksi Data")
        col_edit, col_delete = st.columns(2)
        
        with col_edit:
            st.write("📝 **Edit Nama Barang**")
            id_edit = st.number_input("Masukkan ID untuk Edit", min_value=0, step=1, key="edit_id_input")
            nama_baru = st.text_input("Nama Barang Baru", key="edit_nama_input")
            if st.button("Update Nama"):
                if nama_baru:
                    conn.execute("UPDATE AWE_DB.peminjaman SET nama_barang = ? WHERE id = ?", (nama_baru, id_edit))
                    st.success(f"ID {id_edit} berhasil diupdate.")
                    st.rerun()

        with col_delete:
            st.write("🗑️ **Hapus Data**")
            id_hapus = st.number_input("Masukkan ID untuk Hapus", min_value=0, step=1, key="delete_id_input")
            if st.button("Hapus Data Permanen", type="primary", key="delete_btn"):
                conn.execute("DELETE FROM AWE_DB.peminjaman WHERE id = ?", (id_hapus,))
                st.warning(f"Data ID {id_hapus} telah dihapus.")
                st.rerun()
    else:
        st.info("Belum ada data tersedia.")