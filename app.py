import streamlit as st

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
st.set_page_config(page_title="Maravi Surebet Calc", page_icon="💰")

if "capital_total" not in st.session_state:
    st.session_state["capital_total"] = 200000.0

# --- LÓGICA DE LIMPIEZA ---
def limpiar_campos():
    st.session_state["capital_total"] = 200000.0
    for i in range(3):
        st.session_state[f"cuota_{i}"] = 2.00

st.title("📊 Calculadora de Surebets Pro")
st.markdown("---")

# --- BARRA LATERAL ---
st.sidebar.markdown("### Configuración")
if st.sidebar.button("🧹 Limpiar Campos"):
    limpiar_campos()
    st.rerun()

capital_total = st.sidebar.number_input(
    "Capital Total a Invertir ($)", 
    min_value=1000.0, 
    step=1000.0,
    key="capital_total" 
)

num_opciones = st.sidebar.selectbox("Número de resultados", [2, 3], index=0)

modo_redondeo = st.sidebar.radio(
    "Seleccionar redondeo:",
    ["Sin redondear", "A 100", "A 500", "A 1.000", "A 5.000", "A 10.000"],
    index=3 # Ajustado al nuevo índice
)

# Mapeo de factores actualizado
factores = {
    "Sin redondear": 1, 
    "A 100": 100, 
    "A 500": 500, 
    "A 1.000": 1000, 
    "A 5.000": 5000, 
    "A 10.000": 10000
}
factor = factores[modo_redondeo]

st.subheader("Configuración de Cuotas")
cols = st.columns(num_opciones)
cuotas = []

for i in range(num_opciones):
    with cols[i]:
        if f"cuota_{i}" not in st.session_state:
            st.session_state[f"cuota_{i}"] = 2.00
        c = st.number_input(f"Cuota {i+1}", min_value=1.01, step=0.01, format="%.2f", key=f"cuota_{i}")
        cuotas.append(c)

# --- CÁLCULOS Y RESULTADOS ---
L = sum([1/c for c in cuotas])
es_surebet = L < 1

if es_surebet:
    st.success(f"✅ ¡SUREBET DETECTADA! Rentabilidad: {((1/L)-1)*100:.2f}%")
    
    with st.container(border=True):
        st.subheader("⚖️ Distribución Equilibrada")
        
        # Lógica de Balanceo
        monto_ideal_1 = capital_total / (cuotas[0] * L)
        
        if factor == 1:
            apuesta_1 = monto_ideal_1
            formato = ":,.2f"
        else:
            apuesta_1 = round(monto_ideal_1 / factor) * factor
            formato = ":,.0f"
            
        apuesta_2 = capital_total - apuesta_1
        apuestas_balanceadas = [apuesta_1, apuesta_2]
        
        for i, monto in enumerate(apuestas_balanceadas):
            # Formateamos el monto primero
            if factor == 1:
                texto_monto = f"${monto:,.2f}"
            else:
                texto_monto = f"${monto:,.0f}"
                
            st.write(f"👉 **Opción {i+1}**: **{texto_monto}**")

    with st.expander("📊 Ver detalles de retorno", expanded=True):
        res_cols = st.columns(num_opciones)
        for i, cuota in enumerate(cuotas):
            monto = apuestas_balanceadas[i]
            retorno = monto * cuota
            ganancia = retorno - capital_total
            perc = (ganancia / capital_total) * 100
            with res_cols[i]:
                st.metric(f"Opc {i+1}", f"${retorno:,.0f}", f"{perc:.2f}%")
else:
    st.error("❌ No es una Surebet.")