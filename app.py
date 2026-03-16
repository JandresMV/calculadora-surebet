import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- BLOQUE DE SEGURIDAD PROFESIONAL ---
def check_password():
    try:
        if "password" not in st.secrets:
            return True
    except Exception:
        return True 

    def password_entered():
        if st.session_state["password_input"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Acceso Protegido", type="password", on_change=password_entered, key="password_input")
        return False
    return st.session_state.get("password_correct", False)

if not check_password():
    st.stop()

# --- CONFIGURACIÓN Y ESTADO INICIAL ---
st.set_page_config(page_title="Maravi Surebet Pro", page_icon="💰", layout="wide")

if "capital_total" not in st.session_state:
    st.session_state["capital_total"] = 200000.0

if "registrado_exitoso" not in st.session_state:
    st.session_state["registrado_exitoso"] = False

# --- LÓGICA DE LIMPIEZA ---
def limpiar_campos():
    st.session_state["capital_total"] = 200000.0
    st.session_state["registrado_exitoso"] = False
    for i in range(3):
        if f"cuota_{i}" in st.session_state:
            st.session_state[f"cuota_{i}"] = 2.00
    st.rerun()

st.title("📊 Maraví Digital - Surebets Pro")
st.markdown("---")

# --- BARRA LATERAL ---
st.sidebar.markdown("### Configuración General")
if st.sidebar.button("🧹 Limpiar Calculadora"):
    limpiar_campos()

capital_base = st.sidebar.number_input(
    "Capital Total Sugerido ($)", 
    min_value=1000.0, 
    step=1000.0,
    key="capital_total" 
)

num_opciones = st.sidebar.selectbox("Número de resultados", [2, 3], index=0)

modo_redondeo = st.sidebar.radio(
    "Seleccionar redondeo:",
    ["Sin redondear", "A 100", "A 500", "A 1.000", "A 5.000", "A 10.000"],
    index=3 
)

factores = {
    "Sin redondear": 1, "A 100": 100, "A 500": 500, 
    "A 1.000": 1000, "A 5.000": 5000, "A 10.000": 10000
}
factor = factores[modo_redondeo]

# --- ENTRADA DE CUOTAS Y CASAS ---
casas_disponibles = ["Wplay", "Betano", "Betsson", "Betplay"]
st.subheader("Configuración de Cuotas")
cols = st.columns(num_opciones)
cuotas = []
casas_seleccionadas = []

for i in range(num_opciones):
    with cols[i]:
        casa = st.selectbox(f"Casa Opción {i+1}", casas_disponibles, key=f"casa_sel_{i}")
        casas_seleccionadas.append(casa)
        
        if f"cuota_{i}" not in st.session_state:
            st.session_state[f"cuota_{i}"] = 2.00
        c = st.number_input(f"Cuota {i+1}", min_value=1.01, step=0.01, format="%.2f", key=f"cuota_{i}", on_change=lambda: st.session_state.update({"registrado_exitoso": False}))
        cuotas.append(c)

# --- LÓGICA DE CÁLCULO ---
probabilidades = [1/c for c in cuotas]
L = sum(probabilidades)
es_surebet = L < 1
casas_unicas = len(set(casas_seleccionadas)) == num_opciones

if es_surebet:
    if not casas_unicas:
        st.warning("⚠️ ¡Atención! Debes seleccionar casas de apuestas diferentes para cada opción.")
    else:
        rentabilidad_teorica = ((1/L)-1)*100
        st.success(f"✅ ¡SUREBET DETECTADA! Rentabilidad Teórica: {rentabilidad_teorica:.2f}%")
        
        apuestas_balanceadas = []
        for c in cuotas:
            monto_ideal = capital_base / (c * L)
            monto_redondeado = round(monto_ideal / factor) * factor if factor > 1 else monto_ideal
            apuestas_balanceadas.append(monto_redondeado)
        
        capital_real_ajustado = sum(apuestas_balanceadas)

        with st.container(border=True):
            st.subheader("⚖️ Distribución de Apuestas")
            for i, monto in enumerate(apuestas_balanceadas):
                texto_monto = f"${monto:,.2f}" if factor == 1 else f"${monto:,.0f}"
                st.write(f"👉 **{casas_seleccionadas[i]}**: **{texto_monto}** (Cuota {cuotas[i]})")
            st.info(f"💰 **Inversión Total Real (Ajustada):** ${capital_real_ajustado:,.0f}")

        # --- MÓDULO DE RETORNO (RESTAURADO) ---
        with st.expander("📊 Detalles de Retorno Potencial", expanded=True):
            res_cols = st.columns(num_opciones)
            for i, cuota in enumerate(cuotas):
                monto = apuestas_balanceadas[i]
                retorno = monto * cuota
                ganancia = retorno - capital_real_ajustado
                perc = (ganancia / capital_real_ajustado) * 100
                with res_cols[i]:
                    st.metric(f"Si gana {casas_seleccionadas[i]}", f"${retorno:,.0f}", f"{perc:.2f}%")

        # --- REGISTRO CON VALIDACIÓN ---
        st.markdown("---")
        if not st.session_state["registrado_exitoso"]:
            if st.button("💾 Registrar esta Operación", use_container_width=True):
                archivo = "historial_apuestas.csv"
                fecha_id = datetime.now().strftime("%Y%m%d")
                
                if os.path.exists(archivo):
                    df_ex = pd.read_csv(archivo, dtype={'ID': str})
                    jugadas_hoy = df_ex[df_ex['ID'].str.startswith(fecha_id, na=False)]
                    secuencial = len(jugadas_hoy) + 1
                else:
                    secuencial = 1
                    
                nueva_fila = {
                    "ID": f"{fecha_id}{secuencial:03d}",
                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Casa_1": casas_seleccionadas[0], "Cuota_1": cuotas[0], "Apuesta_1": apuestas_balanceadas[0],
                    "Casa_2": casas_seleccionadas[1], "Cuota_2": cuotas[1], "Apuesta_2": apuestas_balanceadas[1],
                    "Inversion_Total": capital_real_ajustado,
                    "Estado": "Abierta", "Ganador Final": "-", "Retorno Final": 0.0, "Rentabilidad": 0.0
                }
                
                df_n = pd.DataFrame([nueva_fila])
                df_n.to_csv(archivo, mode='a', header=not os.path.exists(archivo), index=False)
                st.session_state["registrado_exitoso"] = True
                st.rerun()
        else:
            st.info("✅ Surebet Guardada.")
else:
    st.error("❌ No es una Surebet.")

# --- MÓDULO DE LIQUIDACIÓN Y VISUALIZACIÓN ---
archivo_csv = "historial_apuestas.csv"
if os.path.exists(archivo_csv):
    st.markdown("---")
    st.header("🏁 Liquidación de Apuestas")
    df_cierre = pd.read_csv(archivo_csv, dtype={'ID': str})
    
    # Asegurar que las columnas existan si el CSV es antiguo
    columnas_nuevas = ["Ganador Final", "Retorno Final", "Rentabilidad"]
    for col in columnas_nuevas:
        if col not in df_cierre.columns:
            df_cierre[col] = 0.0 if col != "Ganador Final" else "-"

    pendientes = df_cierre[df_cierre['Estado'] == 'Abierta']
    
    if not pendientes.empty:
        id_sel = st.selectbox("Apuesta a cerrar:", pendientes['ID'].tolist())
        datos = pendientes[pendientes['ID'] == id_sel].iloc[0]
        
        btn_c1, btn_c2 = st.columns(2)
        
        def procesar_cierre(idx_id, num_ganador):
            df_full = pd.read_csv(archivo_csv, dtype={'ID': str})
            idx = df_full.index[df_full['ID'] == idx_id].tolist()[0]
            
            inversion = df_full.at[idx, 'Inversion_Total']
            cuota = df_full.at[idx, f'Cuota_{num_ganador}']
            apuesta = df_full.at[idx, f'Apuesta_{num_ganador}']
            
            ganancia_neta = (apuesta * cuota) - inversion
            rentabilidad = (ganancia_neta / inversion) * 100
            
            df_full.at[idx, 'Estado'] = 'Cerrada'
            df_full.at[idx, 'Ganador Final'] = df_full.at[idx, f'Casa_{num_ganador}']
            df_full.at[idx, 'Retorno Final'] = round(ganancia_neta, 2)
            df_full.at[idx, 'Rentabilidad'] = round(rentabilidad, 2)
            
            df_full.to_csv(archivo_csv, index=False)
            st.rerun()

        if btn_c1.button(f"Ganó {datos['Casa_1']}", use_container_width=True):
            procesar_cierre(id_sel, 1)
        if btn_c2.button(f"Ganó {datos['Casa_2']}", use_container_width=True):
            procesar_cierre(id_sel, 2)
    
    st.markdown("---")
    st.subheader("📜 Historial Completo")
    
    # 1. Hacemos una copia para no alterar los cálculos originales
    df_display = df_cierre.copy()
    
    # 2. Formateamos las columnas asegurando que siempre tengan el símbolo
    def formato_moneda(x):
        try:
            val = float(x)
            if val == 0: return "-"
            # Formato: $ + separador de miles (punto)
            return f"$ {val:,.0f}".replace(",", ".")
        except:
            return "-"

    def formato_porcentaje(x):
        try:
            val = float(x)
            if val == 0: return "-"
            # Formato: número con 2 decimales + símbolo %
            return f"{val:.2f} %".replace(".", ",")
        except:
            return "-"

    # Aplicamos los formatos
    cols_moneda = ["Apuesta_1", "Apuesta_2", "Inversion_Total", "Retorno Final"]
    for col in cols_moneda:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(formato_moneda)
            
    if "Rentabilidad" in df_display.columns:
        df_display["Rentabilidad"] = df_display["Rentabilidad"].apply(formato_porcentaje)
        
    # Limpiamos los campos de texto
    if "Ganador Final" in df_display.columns:
        df_display["Ganador Final"] = df_display["Ganador Final"].replace("None", "-")

    # 3. Mostrar la tabla
    st.dataframe(df_display, use_container_width=True)