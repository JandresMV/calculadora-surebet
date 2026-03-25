import streamlit as st
import pandas as pd
import os
import gspread
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- CONFIGURACIÓN INICIAL (Debe ir primero) ---
st.set_page_config(page_title="Maravi Surebet Pro", page_icon="💰", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }
    h1 { margin-top: 0.2rem; margin-bottom: 0.6rem; }
</style>
""", unsafe_allow_html=True)

# --- BLOQUE DE SEGURIDAD DINÁMICO ---
def is_running_locally():
    """Detecta si el script se está ejecutando localmente."""
    # En Streamlit Cloud o entornos remotos, suele haber secretos configurados o variables de entorno específicas
    return not os.path.exists(".streamlit/secrets.toml") and "STREAMLIT_RUNTIME_ENV_REMOTE" not in os.environ

def check_password():
    """Solo exige contraseña si no se está ejecutando en local."""
    if is_running_locally():
        return True
        
    if "password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password_input"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 Acceso Protegido - Maravi Digital", type="password", on_change=password_entered, key="password_input")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 Contraseña incorrecta")
        return False
    return st.session_state.get("password_correct", False)

if not check_password():
    st.stop()

archivo_excel = "registro_apuestas.xlsx"
archivo_csv = "historial_apuestas.csv"
archivo_sheet_id = "google_sheet_id.txt"
hoja_operaciones = "Operaciones"
hoja_movimientos = "Movimientos"
CASAS_DISPONIBLES = ["1xBet", "Betano", "Betplay", "Betsson", "Codere", "Rushbet", "Stake", "Wplay"]

# --- LÓGICA DE NEGOCIO ---
def calcular_surebet(capital, cuotas, factor_redondeo):
    """Calcula la rentabilidad y distribución de apuestas para 2 opciones."""
    try:
        probabilidades = [1/c for c in cuotas]
        L = sum(probabilidades)
        if L >= 1:
            return None  # No es surebet
        
        rentabilidad = ((1/L) - 1) * 100
        apuestas_raw = [capital / (c * L) for c in cuotas]
        
        # Aplicar redondeo
        if factor_redondeo > 1:
            apuestas = [round(a / factor_redondeo) * factor_redondeo for a in apuestas_raw]
        else:
            apuestas = apuestas_raw
            
        inversion_real = sum(apuestas)
        retornos_totales = [apuestas[i] * cuotas[i] for i in range(len(cuotas))]
        ganancias_netas = [retornos_totales[i] - inversion_real for i in range(len(cuotas))]
        return {
            "rentabilidad": rentabilidad,
            "apuestas": apuestas,
            "inversion_real": inversion_real,
            "retornos_totales": retornos_totales,
            "ganancias_netas": ganancias_netas
        }
    except ZeroDivisionError:
        return None

def liquidar_linea(row):
    """Recalcula métricas de cierre para una fila de datos si tiene ganador."""
    try:
        # Asegurar tipos numéricos y recalcular inversión automáticamente
        ap1 = pd.to_numeric(row.get("Apuesta_1", 0), errors='coerce') or 0.0
        ap2 = pd.to_numeric(row.get("Apuesta_2", 0), errors='coerce') or 0.0
        c1 = pd.to_numeric(row.get("Cuota_1", 0), errors='coerce') or 0.0
        c2 = pd.to_numeric(row.get("Cuota_2", 0), errors='coerce') or 0.0

        row["Inversion_Total"] = ap1 + ap2

        ganador = str(row.get("Ganador Final", "")).strip()
        
        # Si se borra el ganador, revertir estado a Abierta para que aparezca en el cierre rápido
        if not ganador or ganador.lower() in ["nan", "none", "-", ""]:
            row["Estado"] = "Abierta"
            row["Ganador Final"] = "-"
            row["Retorno Final"] = 0.0
            row["Rentabilidad"] = 0.0
        # Solo calculamos si está cerrada y el ganador coincide con una de las casas
        elif row["Estado"] == "Cerrada" and ganador in [row["Casa_1"], row["Casa_2"]]:
            inv = float(row["Inversion_Total"])
            if inv > 0:
                # Calcular ganancia real basada en la cuota y apuesta editada
                if ganador == row["Casa_1"]:
                    ganancia = (ap1 * c1) - inv
                else:
                    ganancia = (ap2 * c2) - inv
                
                row["Retorno Final"] = round(ganancia, 2)
                row["Rentabilidad"] = round((ganancia / inv) * 100, 2)
    except (ValueError, KeyError, TypeError):
        pass 
    return row

def obtener_sheet_id():
    if "google_sheet_id" in st.secrets:
        return st.secrets["google_sheet_id"]
    if os.path.exists(archivo_sheet_id):
        try:
            with open(archivo_sheet_id, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None

def guardar_sheet_id(sheet_id):
    try:
        with open(archivo_sheet_id, "w", encoding="utf-8") as f:
            f.write(sheet_id)
    except Exception:
        pass

def obtener_cliente_gsheets():
    if "gcp_service_account" not in st.secrets:
        return None
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"], scopes=scopes)

def obtener_spreadsheet():
    client = obtener_cliente_gsheets()
    if not client:
        return None
    sheet_id = obtener_sheet_id()
    if sheet_id:
        return client.open_by_key(sheet_id)
    sheet = client.create("Maravi Surebet Pro")
    guardar_sheet_id(sheet.id)
    st.info(f"Se creó el Google Sheet. ID: {sheet.id}")
    return sheet

def leer_hoja(sheet, nombre):
    try:
        ws = sheet.worksheet(nombre)
    except Exception:
        ws = sheet.add_worksheet(title=nombre, rows=1, cols=20)
    data = ws.get_all_values()
    if not data:
        return pd.DataFrame()
    headers = data[0]
    rows = data[1:]
    return pd.DataFrame(rows, columns=headers)

def escribir_hoja(sheet, nombre, df):
    ws = sheet.worksheet(nombre)
    df_safe = df.copy()
    if df_safe.empty:
        ws.clear()
        return
    df_safe = df_safe.fillna("")
    ws.update([df_safe.columns.tolist()] + df_safe.astype(str).values.tolist())

def cargar_datos():
    sheet = obtener_spreadsheet()
    if sheet:
        df_ops = leer_hoja(sheet, hoja_operaciones)
        df_mov = leer_hoja(sheet, hoja_movimientos)
        return df_ops, df_mov
    if os.path.exists(archivo_excel):
        try:
            df_ops = pd.read_excel(archivo_excel, sheet_name=hoja_operaciones, dtype={'ID': str})
        except Exception:
            df_ops = pd.DataFrame()
        try:
            df_mov = pd.read_excel(archivo_excel, sheet_name=hoja_movimientos)
        except Exception:
            df_mov = pd.DataFrame()
        return df_ops, df_mov
    if os.path.exists(archivo_csv):
        try:
            df_ops = pd.read_csv(archivo_csv, dtype={'ID': str})
        except Exception:
            df_ops = pd.DataFrame()
        return df_ops, pd.DataFrame()
    return pd.DataFrame(), pd.DataFrame()

def guardar_respaldo_excel(df_ops, df_mov):
    try:
        with pd.ExcelWriter(archivo_excel, engine="openpyxl") as writer:
            df_ops.to_excel(writer, sheet_name=hoja_operaciones, index=False)
            df_mov.to_excel(writer, sheet_name=hoja_movimientos, index=False)
        return True
    except PermissionError:
        st.error("El archivo 'registro_apuestas.xlsx' está abierto. Ciérralo y vuelve a intentar.")
        return False

def guardar_gsheets(df_ops, df_mov):
    sheet = obtener_spreadsheet()
    if not sheet:
        st.error("No hay credenciales de Google Sheets configuradas.")
        return False
    for nombre in [hoja_operaciones, hoja_movimientos]:
        try:
            sheet.worksheet(nombre)
        except Exception:
            sheet.add_worksheet(title=nombre, rows=1, cols=20)
    escribir_hoja(sheet, hoja_operaciones, df_ops)
    escribir_hoja(sheet, hoja_movimientos, df_mov)
    return True

def guardar_todo(df_ops, df_mov):
    ok = guardar_gsheets(df_ops, df_mov)
    guardar_respaldo_excel(df_ops, df_mov)
    return ok

def guardar_excel(df_ops, df_mov):
    return guardar_todo(df_ops, df_mov)

def normalizar_historial(df):
    defaults = {
        "ID": "",
        "Fecha": "",
        "Tipo_Operacion": "Surebet",
        "Modalidad": "N/A",
        "Casa_1": "",
        "Cuota_1": 0.0,
        "Apuesta_1": 0.0,
        "Casa_2": "",
        "Cuota_2": 0.0,
        "Apuesta_2": 0.0,
        "Estado": "Abierta",
        "Ganador Final": "-",
        "Retorno Final": 0.0,
        "Rentabilidad": 0.0,
        "Inversion_Total": 0.0
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df

def normalizar_movimientos(df):
    defaults = {
        "Fecha": "",
        "Casa": "",
        "Tipo": "Depósito",
        "Monto": 0.0,
        "Nota": ""
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df

def sincronizar_cambios_editor():
    """Sincroniza cambios del data_editor al CSV y actualiza cálculos."""
    if "editor_historial" in st.session_state:
        edits = st.session_state["editor_historial"]
        df_actual, df_mov = cargar_datos()
        df_actual = normalizar_historial(df_actual)
        mapa_indices = st.session_state.get("mapa_indices")
        
        # Aplicar ediciones de celdas
        for row_idx, row_changes in edits["edited_rows"].items():
            row_idx = int(row_idx)
            actual_idx = mapa_indices[row_idx] if mapa_indices and row_idx < len(mapa_indices) else row_idx
            for col_name, new_val in row_changes.items():
                if col_name == "N°":
                    continue
                df_actual.at[actual_idx, col_name] = new_val
            
            # Lógica inteligente: Si cambiaron datos clave, intentar recalcular liquidación
            df_actual.iloc[actual_idx] = liquidar_linea(df_actual.iloc[actual_idx])
        
        # Aplicar eliminaciones
        if edits["deleted_rows"]:
            indices_eliminar = [
                mapa_indices[i] if mapa_indices and i < len(mapa_indices) else i
                for i in edits["deleted_rows"]
            ]
            df_actual = df_actual.drop(indices_eliminar)
            
        if guardar_excel(df_actual, df_mov):
            st.toast("Cambios guardados y recálculo aplicado", icon="💾")

def sincronizar_movimientos_editor():
    if "editor_movimientos" in st.session_state:
        edits = st.session_state["editor_movimientos"]
        df_ops, df_mov = cargar_datos()
        df_ops = normalizar_historial(df_ops)
        df_mov = normalizar_movimientos(df_mov)

        for row_idx, row_changes in edits["edited_rows"].items():
            row_idx = int(row_idx)
            for col_name, new_val in row_changes.items():
                df_mov.at[row_idx, col_name] = new_val

        if edits["deleted_rows"]:
            df_mov = df_mov.drop(edits["deleted_rows"])

        if guardar_excel(df_ops, df_mov):
            st.toast("Cambios de movimientos guardados", icon="💾")

# --- INTERFAZ DE USUARIO ---
st.title("📊 Maraví Digital - Surebets Pro")

# Sidebar: Configuración
with st.sidebar:
    st.header("⚙️ Configuración")
    capital_base = st.number_input("Capital Base ($)", min_value=1000.0, value=100000.0, step=1000.0)
    modo_redondeo = st.selectbox("Redondeo de Apuesta", ["Sin redondear", "A 100", "A 500", "A 1.000", "A 5.000", "A 10.000"], index=3)
    factores = {"Sin redondear": 1, "A 100": 100, "A 500": 500, "A 1.000": 1000, "A 5.000": 5000, "A 10.000": 10000}
    factor = factores[modo_redondeo]
    st.divider()
    st.caption("Versión 2.0 - Optimizado")

# Layout Principal: Calculadora (2 Opciones)
st.markdown("### 🧮 Calculadora de Oportunidades")
panel_izq, panel_der = st.columns([4, 6])
cuotas = []
casas_seleccionadas = []
ahora_col = datetime.now(ZoneInfo("America/Bogota"))

with panel_izq:
    tabs = st.tabs(["Surebet", "Maquillaje"])
    with tabs[0]:
        fecha_evento = st.date_input("Fecha del evento", value=ahora_col.date())
        s1, s2 = st.columns(2)
        with s1:
            casa_1 = st.selectbox("Casa 1", CASAS_DISPONIBLES, key="c1")
        with s2:
            cuota_1 = st.number_input("Cuota 1", min_value=1.01, max_value=25.0, value=2.00, step=0.01, format="%.2f", help="Usa las flechas del teclado ↑ ↓ para ajustar rápidamente.")
        casas_seleccionadas.append(casa_1)
        cuotas.append(cuota_1)

        s3, s4 = st.columns(2)
        with s3:
            casa_2 = st.selectbox("Casa 2", CASAS_DISPONIBLES, key="c2", index=1)
        with s4:
            cuota_2 = st.number_input("Cuota 2", min_value=1.01, max_value=25.0, value=2.00, step=0.01, format="%.2f", help="Usa las flechas del teclado ↑ ↓ para ajustar rápidamente.")
        casas_seleccionadas.append(casa_2)
        cuotas.append(cuota_2)

    with tabs[1]:
        m1, m2 = st.columns(2)
        with m1:
            fecha_evento = st.date_input("Fecha del evento", value=ahora_col.date(), key="fecha_evento_maquillaje")
        with m2:
            modalidad_maquillaje = st.selectbox("Modalidad", ["Simple", "Combinada"], key="mod_maquillaje")

        m3, m4 = st.columns(2)
        with m3:
            casa_maquillaje = st.selectbox("Casa", CASAS_DISPONIBLES, key="casa_maquillaje")
        with m4:
            cuota_maquillaje = st.number_input("Cuota", min_value=1.01, max_value=1000.0, value=2.00, step=0.01, format="%.2f", key="cuota_maquillaje")
        apuesta_maquillaje = st.number_input("Apuesta", min_value=1000.0, value=10000.0, step=1000.0, key="apuesta_maquillaje")

        firma_maquillaje = f"{fecha_evento}-{modalidad_maquillaje}-{casa_maquillaje}-{cuota_maquillaje}-{apuesta_maquillaje}"
        ya_registrado_maquillaje = st.session_state.get("ultimo_maquillaje") == firma_maquillaje

        if st.button("💾 Registrar maquillaje", use_container_width=True, key="btn_maquillaje", disabled=ya_registrado_maquillaje):
            fecha_id = fecha_evento.strftime("%Y%m%d")
            df_ex, df_mov = cargar_datos()
            df_ex = normalizar_historial(df_ex)
            secuencial = len(df_ex[df_ex['ID'].str.startswith(fecha_id, na=False)]) + 1 if not df_ex.empty else 1
            nueva_fila = {
                "ID": f"{fecha_id}{secuencial:03d}", "Fecha": fecha_evento.strftime("%Y-%m-%d"),
                "Tipo_Operacion": "Maquillaje", "Modalidad": modalidad_maquillaje,
                "Casa_1": casa_maquillaje, "Cuota_1": cuota_maquillaje, "Apuesta_1": apuesta_maquillaje,
                "Casa_2": casa_maquillaje, "Cuota_2": 1.0, "Apuesta_2": 0.0,
                "Inversion_Total": apuesta_maquillaje, "Estado": "Abierta", "Ganador Final": "-", "Retorno Final": 0.0, "Rentabilidad": 0.0
            }
            df_nueva = pd.DataFrame([nueva_fila])
            df_ex = pd.concat([df_ex, df_nueva], ignore_index=True) if not df_ex.empty else df_nueva
            if guardar_excel(df_ex, df_mov):
                st.session_state["ultimo_maquillaje"] = firma_maquillaje
                st.success("Registrado!")
                st.rerun()

    if "fecha_evento" not in locals():
        fecha_evento = st.session_state.get("fecha_evento_maquillaje", ahora_col.date())

with panel_der:
    st.markdown("### 📈 Rentabilidad")
    resultado = calcular_surebet(capital_base, cuotas, factor)
    
    if resultado:
        st.metric(label="Rentabilidad Estimada", value=f"{resultado['rentabilidad']:.2f}%", delta="SUREBET DETECTADA")
        
        st.write(f"**{casa_1}**: ${resultado['apuestas'][0]:,.0f}")
        st.write(f"Retorno total: ${resultado['retornos_totales'][0]:,.0f} | Ganancia neta: ${resultado['ganancias_netas'][0]:,.0f}")
        st.write(f"**{casa_2}**: ${resultado['apuestas'][1]:,.0f}")
        st.write(f"Retorno total: ${resultado['retornos_totales'][1]:,.0f} | Ganancia neta: ${resultado['ganancias_netas'][1]:,.0f}")
        st.markdown(f"**Total Inversión**: ${resultado['inversion_real']:,.0f}")
        
        firma_operacion = f"{casas_seleccionadas}-{cuotas}-{resultado['apuestas']}"
        ya_registrado = st.session_state.get("ultimo_registro") == firma_operacion

        if st.button("💾 Registrar Operación", type="primary", use_container_width=True, disabled=ya_registrado):
            fecha_id = fecha_evento.strftime("%Y%m%d")
            df_ex, df_mov = cargar_datos()
            df_ex = normalizar_historial(df_ex)
            secuencial = len(df_ex[df_ex['ID'].str.startswith(fecha_id, na=False)]) + 1 if not df_ex.empty else 1
            
            nueva_fila = {
                "ID": f"{fecha_id}{secuencial:03d}", "Fecha": fecha_evento.strftime("%Y-%m-%d"),
                "Tipo_Operacion": "Surebet", "Modalidad": "N/A",
                "Casa_1": casas_seleccionadas[0], "Cuota_1": cuotas[0], "Apuesta_1": resultado['apuestas'][0],
                "Casa_2": casas_seleccionadas[1], "Cuota_2": cuotas[1], "Apuesta_2": resultado['apuestas'][1],
                "Inversion_Total": resultado['inversion_real'], "Estado": "Abierta", "Ganador Final": "-", "Retorno Final": 0.0, "Rentabilidad": 0.0
            }
            df_nueva = pd.DataFrame([nueva_fila])
            df_ex = pd.concat([df_ex, df_nueva], ignore_index=True) if not df_ex.empty else df_nueva
            if guardar_excel(df_ex, df_mov):
                st.session_state["ultimo_registro"] = firma_operacion
                st.success("Registrado!")
                st.rerun()
    else:
        st.metric(label="Rentabilidad", value="--", delta="-NO RENTABLE", delta_color="normal")
        st.warning("Sin oportunidad.")

# --- GESTIÓN DEL HISTORIAL ---
st.divider()
st.header("🏁 Gestión del Historial")
    
df_historial, df_movimientos = cargar_datos()
df_historial = normalizar_historial(df_historial)
df_movimientos = normalizar_movimientos(df_movimientos)

st.subheader("📋 Registro Detallado")
st.info("💡 Edita 'Estado' y 'Ganador Final' directamente aquí para recalcular sin usar el cierre rápido.")

opciones_tipo = ["Todos"] + sorted(df_historial["Tipo_Operacion"].dropna().astype(str).unique().tolist())
opciones_modalidad = ["Todos"] + sorted(df_historial["Modalidad"].dropna().astype(str).unique().tolist())
opciones_ganador = ["Todos"] + sorted(df_historial["Ganador Final"].dropna().astype(str).unique().tolist())
opciones_estado = ["Todos", "Abierta", "Cerrada"]

hoy_col = ahora_col.date()
tipo_rango = st.session_state.get("filtro_rango_tipo", "Todo")
rango_personalizado = st.session_state.get("filtro_rango_personalizado", (hoy_col, hoy_col))
filtro_ganador = st.session_state.get("filtro_ganador", "Todos")
filtro_estado = st.session_state.get("filtro_estado", "Todos")
filtro_tipo = st.session_state.get("filtro_tipo_op", "Todos")
filtro_modalidad = st.session_state.get("filtro_modalidad", "Todos")

f1, f2, f3, f4, f5, f6 = st.columns([1, 1, 1, 1, 1, 1.2])
with f1:
    st.selectbox("Fecha", ["Todo", "Día", "Semana", "Mes", "Personalizada"], key="filtro_rango_tipo")
with f2:
    st.selectbox("Ganador", opciones_ganador, key="filtro_ganador")
with f3:
    st.selectbox("Estado", opciones_estado, key="filtro_estado")
with f4:
    st.selectbox("Tipo", opciones_tipo, key="filtro_tipo_op")
with f5:
    st.selectbox("Modalidad", opciones_modalidad, key="filtro_modalidad")
with f6:
    if st.session_state.get("filtro_rango_tipo") == "Personalizada":
        st.date_input("Rango", value=rango_personalizado, key="filtro_rango_personalizado")
    else:
        st.markdown("")
df_filtrado = df_historial.copy()

fecha_inicio = None
fecha_fin = None
if tipo_rango == "Día":
    fecha_inicio = hoy_col
    fecha_fin = hoy_col
elif tipo_rango == "Semana":
    fecha_inicio = hoy_col - timedelta(days=6)
    fecha_fin = hoy_col
elif tipo_rango == "Mes":
    fecha_inicio = hoy_col.replace(day=1)
    fecha_fin = hoy_col
elif tipo_rango == "Personalizada":
    if isinstance(rango_personalizado, tuple) and len(rango_personalizado) == 2:
        fecha_inicio, fecha_fin = rango_personalizado

if fecha_inicio and fecha_fin:
    fechas = pd.to_datetime(df_filtrado["Fecha"], errors="coerce").dt.date
    df_filtrado = df_filtrado[(fechas >= fecha_inicio) & (fechas <= fecha_fin)]
if filtro_tipo != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Tipo_Operacion"].astype(str) == filtro_tipo]
if filtro_modalidad != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Modalidad"].astype(str) == filtro_modalidad]
if filtro_ganador != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Ganador Final"].astype(str) == filtro_ganador]
if filtro_estado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Estado"].astype(str) == filtro_estado]

total_inversion = pd.to_numeric(df_filtrado.get("Inversion_Total", 0), errors="coerce").fillna(0).sum()
total_ganancia = pd.to_numeric(df_filtrado.get("Retorno Final", 0), errors="coerce").fillna(0).sum()
rentabilidad_total = (total_ganancia / total_inversion * 100) if total_inversion else 0.0
t1, t2, t3 = st.columns(3)
t1.metric("Total inversión", f"${total_inversion:,.0f}")
t2.metric("Ganancia neta", f"${total_ganancia:,.0f}")
t3.metric("Rentabilidad", f"{rentabilidad_total:.2f}%")

df_filtrado_display = df_filtrado.copy()
df_filtrado_display.insert(0, "N°", range(1, len(df_filtrado_display) + 1))

st.data_editor(
    df_filtrado_display,
    use_container_width=True,
    num_rows="dynamic",
    disabled=["N°"],
    column_config={
        "N°": st.column_config.NumberColumn("N°", format="%d"),
        "ID": st.column_config.TextColumn("ID", required=True),
        "Tipo_Operacion": st.column_config.SelectboxColumn("Tipo", options=["Surebet", "Maquillaje"], required=True),
        "Modalidad": st.column_config.SelectboxColumn("Modalidad", options=["Simple", "Combinada", "N/A"], required=True),
        "Casa_1": st.column_config.SelectboxColumn("Casa 1", options=CASAS_DISPONIBLES, required=True),
        "Casa_2": st.column_config.SelectboxColumn("Casa 2", options=CASAS_DISPONIBLES, required=True),
        "Estado": st.column_config.SelectboxColumn("Estado", options=["Abierta", "Cerrada"], required=True),
        "Ganador Final": st.column_config.TextColumn("Ganador Final", help="Debe coincidir con una casa"),
        "Rentabilidad": st.column_config.NumberColumn("Rent (%)", format="%.2f"),
        "Retorno Final": st.column_config.NumberColumn("Retorno ($)", format="$%.2f"),
        "Inversion_Total": st.column_config.NumberColumn("Inversión", format="$%.0f"),
        "Apuesta_1": st.column_config.NumberColumn("Apuesta 1", format="$%.0f"),
        "Apuesta_2": st.column_config.NumberColumn("Apuesta 2", format="$%.0f"),
    },
    key="editor_historial",
    on_change=sincronizar_cambios_editor
)
st.session_state["mapa_indices"] = df_filtrado.index.to_list()

# Panel de Cierre Rápido (Simplificado)
pendientes = df_historial[df_historial['Estado'] == 'Abierta']
if not pendientes.empty:
    with st.expander("⚡ Cierre Rápido de Apuestas (Pendientes)"):
        cols_close = st.columns([2, 1, 1])
        with cols_close[0]:
            id_sel = st.selectbox("Selecciona Apuesta", pendientes['ID'].tolist(), format_func=lambda x: f"ID: {x} | {pendientes[pendientes['ID']==x]['Fecha'].values[0]}")
        
        idx = df_historial.index[df_historial['ID'] == id_sel][0]
        row_sel = df_historial.loc[idx]

        with cols_close[1]:
            if st.button(f"🏆 Ganó {row_sel['Casa_1']} (@{row_sel['Cuota_1']})", use_container_width=True):
                df_historial.at[idx, "Ganador Final"] = row_sel['Casa_1']
                df_historial.at[idx, "Estado"] = "Cerrada"
                df_historial.iloc[idx] = liquidar_linea(df_historial.iloc[idx])
                if guardar_excel(df_historial, df_movimientos):
                    st.rerun()
        with cols_close[2]:
            if st.button(f"🏆 Ganó {row_sel['Casa_2']} (@{row_sel['Cuota_2']})", use_container_width=True):
                df_historial.at[idx, "Ganador Final"] = row_sel['Casa_2']
                df_historial.at[idx, "Estado"] = "Cerrada"
                df_historial.iloc[idx] = liquidar_linea(df_historial.iloc[idx])
                if guardar_excel(df_historial, df_movimientos):
                    st.rerun()

st.divider()
st.subheader("💼 Movimientos de Caja")

mc1, mc2, mc3 = st.columns(3)
with mc1:
    mov_fecha = st.date_input("Fecha", value=ahora_col.date(), key="mov_fecha")
with mc2:
    mov_casa = st.selectbox("Casa", CASAS_DISPONIBLES, key="mov_casa")
with mc3:
    mov_tipo = st.selectbox("Tipo", ["Depósito", "Retiro"], key="mov_tipo")

mc4, mc5 = st.columns([1, 2])
with mc4:
    mov_monto = st.number_input("Monto", min_value=0.0, value=0.0, step=1000.0, key="mov_monto")
with mc5:
    mov_nota = st.text_input("Nota", key="mov_nota")

firma_mov = f"{mov_fecha}-{mov_casa}-{mov_tipo}-{mov_monto}-{mov_nota}"
ya_reg_mov = st.session_state.get("ultimo_mov") == firma_mov

if st.button("💾 Registrar movimiento", use_container_width=True, disabled=ya_reg_mov):
    df_ops, df_mov = cargar_datos()
    df_ops = normalizar_historial(df_ops)
    df_mov = normalizar_movimientos(df_mov)
    nueva_fila = {
        "Fecha": mov_fecha.strftime("%Y-%m-%d"),
        "Casa": mov_casa,
        "Tipo": mov_tipo,
        "Monto": mov_monto,
        "Nota": mov_nota
    }
    df_nueva = pd.DataFrame([nueva_fila])
    df_mov = pd.concat([df_mov, df_nueva], ignore_index=True) if not df_mov.empty else df_nueva
    if guardar_excel(df_ops, df_mov):
        st.session_state["ultimo_mov"] = firma_mov
        st.success("Registrado!")
        st.rerun()

st.data_editor(
    df_movimientos,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Fecha": st.column_config.TextColumn("Fecha"),
        "Casa": st.column_config.SelectboxColumn("Casa", options=CASAS_DISPONIBLES),
        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Depósito", "Retiro"]),
        "Monto": st.column_config.NumberColumn("Monto", format="$%.0f"),
        "Nota": st.column_config.TextColumn("Nota")
    },
    key="editor_movimientos",
    on_change=sincronizar_movimientos_editor
)

st.divider()
st.subheader("📥 Importar Excel")
archivo_importado = st.file_uploader("Sube tu archivo XLSX", type=["xlsx"])
if archivo_importado:
    try:
        df_ops_imp = pd.read_excel(archivo_importado, sheet_name=hoja_operaciones, dtype={'ID': str})
    except Exception:
        df_ops_imp = pd.read_excel(archivo_importado, dtype={'ID': str})
    try:
        df_mov_imp = pd.read_excel(archivo_importado, sheet_name=hoja_movimientos)
    except Exception:
        df_mov_imp = pd.DataFrame()

    df_ops_imp = normalizar_historial(df_ops_imp)
    df_mov_imp = normalizar_movimientos(df_mov_imp)

    if st.button("✅ Importar y reemplazar datos", use_container_width=True):
        if guardar_excel(df_ops_imp, df_mov_imp):
            st.success("Datos importados correctamente.")
            st.rerun()

st.divider()
st.subheader("⬇️ Exportar Excel")
df_ops_export, df_mov_export = cargar_datos()
df_ops_export = normalizar_historial(df_ops_export)
df_mov_export = normalizar_movimientos(df_mov_export)
try:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ops_export.to_excel(writer, sheet_name=hoja_operaciones, index=False)
        df_mov_export.to_excel(writer, sheet_name=hoja_movimientos, index=False)
    buffer.seek(0)
    st.download_button(
        label="Descargar Excel",
        data=buffer,
        file_name=archivo_excel,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
except Exception:
    st.error("No se pudo generar el archivo de exportación.")

# Sistema de borrado con confirmación
if st.button("🗑️ Borrar Historial Completo", type="secondary"):
    st.session_state["confirmar_borrado"] = True
    st.rerun()

if st.session_state.get("confirmar_borrado"):
    st.warning("⚠️ ¿Estás seguro? Esta acción eliminará permanentemente todo el historial.")
    col_conf_1, col_conf_2 = st.columns([1, 1])
    with col_conf_1:
        if st.button("✅ Sí, eliminar todo", type="primary", use_container_width=True):
            if os.path.exists(archivo_excel):
                os.remove(archivo_excel)
            if os.path.exists(archivo_csv):
                os.remove(archivo_csv)
            st.session_state["confirmar_borrado"] = False
            st.success("Historial eliminado.")
            st.rerun()
    with col_conf_2:
        if st.button("❌ Cancelar", type="secondary", use_container_width=True):
            st.session_state["confirmar_borrado"] = False
            st.rerun()
