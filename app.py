import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURACIÓN INICIAL (Debe ir primero) ---
st.set_page_config(page_title="Maravi Surebet Pro", page_icon="💰", layout="wide")

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

archivo_csv = "historial_apuestas.csv"
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
            
        return {
            "rentabilidad": rentabilidad,
            "apuestas": apuestas,
            "inversion_real": sum(apuestas)
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

def sincronizar_cambios_editor():
    """Sincroniza cambios del data_editor al CSV y actualiza cálculos."""
    if "editor_historial" in st.session_state:
        edits = st.session_state["editor_historial"]
        df_actual = pd.read_csv(archivo_csv, dtype={'ID': str})
        
        # Aplicar ediciones de celdas
        for row_idx, row_changes in edits["edited_rows"].items():
            row_idx = int(row_idx)
            for col_name, new_val in row_changes.items():
                df_actual.at[row_idx, col_name] = new_val
            
            # Lógica inteligente: Si cambiaron datos clave, intentar recalcular liquidación
            df_actual.iloc[row_idx] = liquidar_linea(df_actual.iloc[row_idx])
        
        # Aplicar eliminaciones
        if edits["deleted_rows"]:
            df_actual = df_actual.drop(edits["deleted_rows"])
            
        df_actual.to_csv(archivo_csv, index=False)
        st.toast("Cambios guardados y recálculo aplicado", icon="💾")

# --- INTERFAZ DE USUARIO ---
st.title("📊 Maraví Digital - Surebets Pro")

# Sidebar: Configuración
with st.sidebar:
    st.header("⚙️ Configuración")
    capital_base = st.number_input("Capital Base ($)", min_value=1000.0, value=100000.0, step=5000.0)
    modo_redondeo = st.selectbox("Redondeo de Apuesta", ["Sin redondear", "A 100", "A 500", "A 1.000", "A 5.000", "A 10.000"], index=3)
    factores = {"Sin redondear": 1, "A 100": 100, "A 500": 500, "A 1.000": 1000, "A 5.000": 5000, "A 10.000": 10000}
    factor = factores[modo_redondeo]
    st.divider()
    st.caption("Versión 2.0 - Optimizado")

# Layout Principal: Calculadora (2 Opciones)
st.markdown("### 🧮 Calculadora de Oportunidades")
c1, c2, c3 = st.columns([1, 1, 0.8])
cuotas = []
casas_seleccionadas = []

with c1:
    casa_1 = st.selectbox("Casa 1", CASAS_DISPONIBLES, key="c1")
    cuota_1 = st.number_input("Cuota 1", min_value=1.01, max_value=25.0, value=2.00, step=0.01, format="%.2f", help="Usa las flechas del teclado ↑ ↓ para ajustar rápidamente.")
    casas_seleccionadas.append(casa_1)
    cuotas.append(cuota_1)

with c2:
    casa_2 = st.selectbox("Casa 2", CASAS_DISPONIBLES, key="c2", index=1)
    cuota_2 = st.number_input("Cuota 2", min_value=1.01, max_value=25.0, value=2.00, step=0.01, format="%.2f", help="Usa las flechas del teclado ↑ ↓ para ajustar rápidamente.")
    casas_seleccionadas.append(casa_2)
    cuotas.append(cuota_2)

# Panel de Resultados
with c3:
    resultado = calcular_surebet(capital_base, cuotas, factor)
    
    if resultado:
        st.metric(label="Rentabilidad Estimada", value=f"{resultado['rentabilidad']:.2f}%", delta="SUREBET DETECTADA")
        
        st.write(f"**{casa_1}**: ${resultado['apuestas'][0]:,.0f}")
        st.write(f"**{casa_2}**: ${resultado['apuestas'][1]:,.0f}")
        st.markdown(f"**Total Inversión**: ${resultado['inversion_real']:,.0f}")
        
        # Control de duplicados: Generar firma única de la operación actual
        firma_operacion = f"{casas_seleccionadas}-{cuotas}-{resultado['apuestas']}"
        ya_registrado = st.session_state.get("ultimo_registro") == firma_operacion

        if st.button("💾 Registrar Operación", type="primary", use_container_width=True, disabled=ya_registrado):
            fecha_id = datetime.now().strftime("%Y%m%d")
            if os.path.exists(archivo_csv):
                df_ex = pd.read_csv(archivo_csv, dtype={'ID': str})
                secuencial = len(df_ex[df_ex['ID'].str.startswith(fecha_id, na=False)]) + 1
            else:
                df_ex = pd.DataFrame()
                secuencial = 1
            
            nueva_fila = {
                "ID": f"{fecha_id}{secuencial:03d}", "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Casa_1": casas_seleccionadas[0], "Cuota_1": cuotas[0], "Apuesta_1": resultado['apuestas'][0],
                "Casa_2": casas_seleccionadas[1], "Cuota_2": cuotas[1], "Apuesta_2": resultado['apuestas'][1],
                "Inversion_Total": resultado['inversion_real'], "Estado": "Abierta", "Ganador Final": "-", "Retorno Final": 0.0, "Rentabilidad": 0.0
            }
            pd.DataFrame([nueva_fila]).to_csv(archivo_csv, mode='a', header=not os.path.exists(archivo_csv), index=False)
            st.session_state["ultimo_registro"] = firma_operacion
            st.success("Registrado!")
            st.rerun()
    else:
        st.metric(label="Rentabilidad", value="--", delta="-NO RENTABLE", delta_color="normal")
        st.warning("Sin oportunidad.")

# --- GESTIÓN DEL HISTORIAL ---
if os.path.exists(archivo_csv):
    st.divider()
    st.header("🏁 Gestión del Historial")
    
    df_historial = pd.read_csv(archivo_csv, dtype={'ID': str})

    st.subheader("📋 Registro Detallado")
    st.info("💡 Edita 'Estado' y 'Ganador Final' directamente aquí para recalcular sin usar el cierre rápido.")
    
    st.data_editor(
        df_historial,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "ID": st.column_config.TextColumn("ID", required=True),
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

    # Panel de Cierre Rápido (Simplificado)
    pendientes = df_historial[df_historial['Estado'] == 'Abierta']
    if not pendientes.empty:
        with st.expander("⚡ Cierre Rápido de Apuestas (Pendientes)"):
            cols_close = st.columns([2, 1, 1])
            with cols_close[0]:
                # Mostramos ID y Fecha en el selector para mayor claridad
                id_sel = st.selectbox("Selecciona Apuesta", pendientes['ID'].tolist(), format_func=lambda x: f"ID: {x} | {pendientes[pendientes['ID']==x]['Fecha'].values[0]}")
            
            idx = df_historial.index[df_historial['ID'] == id_sel][0]
            row_sel = df_historial.loc[idx]

            with cols_close[1]:
                if st.button(f"🏆 Ganó {row_sel['Casa_1']} (@{row_sel['Cuota_1']})", use_container_width=True):
                    df_historial.at[idx, "Ganador Final"] = row_sel['Casa_1']
                    df_historial.at[idx, "Estado"] = "Cerrada"
                    df_historial.iloc[idx] = liquidar_linea(df_historial.iloc[idx])
                    df_historial.to_csv(archivo_csv, index=False)
                    st.rerun()
            with cols_close[2]:
                if st.button(f"🏆 Ganó {row_sel['Casa_2']} (@{row_sel['Cuota_2']})", use_container_width=True):
                    df_historial.at[idx, "Ganador Final"] = row_sel['Casa_2']
                    df_historial.at[idx, "Estado"] = "Cerrada"
                    df_historial.iloc[idx] = liquidar_linea(df_historial.iloc[idx])
                    df_historial.to_csv(archivo_csv, index=False)
                    st.rerun()

    # Sistema de borrado con confirmación
    if st.button("🗑️ Borrar Historial Completo", type="secondary"):
        st.session_state["confirmar_borrado"] = True
        st.rerun()

    if st.session_state.get("confirmar_borrado"):
        st.warning("⚠️ ¿Estás seguro? Esta acción eliminará permanentemente todo el historial.")
        col_conf_1, col_conf_2 = st.columns([1, 1])
        with col_conf_1:
            if st.button("✅ Sí, eliminar todo", type="primary", use_container_width=True):
                if os.path.exists(archivo_csv):
                    os.remove(archivo_csv)
                st.session_state["confirmar_borrado"] = False
                st.success("Historial eliminado.")
                st.rerun()
        with col_conf_2:
            if st.button("❌ Cancelar", type="secondary", use_container_width=True):
                st.session_state["confirmar_borrado"] = False
                st.rerun()