import streamlit as st

# --- BLOQUE DE SEGURIDAD ---
def check_password():
    """Retorna True si el usuario introdujo la clave correcta."""
    def password_entered():
        if st.session_state["password_input"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Acceso Protegido - Ingrese Clave", type="password", on_change=password_entered, key="password_input")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Acceso Protegido - Ingrese Clave", type="password", on_change=password_entered, key="password_input")
        st.error("😕 Clave incorrecta")
        return False
    else:
        return True

# Esta línea es la que bloquea todo lo demás
if not check_password():
    st.stop()

# Configuración estética
st.set_page_config(page_title="Maravi Surebet Calc", page_icon="💰")

st.title("📊 Calculadora de Surebets Pro")
st.markdown("---")

# Entradas de datos
capital_total = st.sidebar.number_input("Capital Total a Invertir ($)", min_value=1000, value=130000, step=1000)
num_opciones = st.sidebar.selectbox("Número de resultados (2 para Tenis, 3 para Fútbol)", [2, 3], index=0)

st.subheader("Configuración de Cuotas")
cols = st.columns(num_opciones)
cuotas = []

for i in range(num_opciones):
    with cols[i]:
        c = st.number_input(f"Cuota Opción {i+1}", min_value=1.01, value=2.00, step=0.01, format="%.2f")
        cuotas.append(c)

# Cálculos matemáticos
probabilidades = [1/c for c in cuotas]
L = sum(probabilidades)
es_surebet = L < 1

if es_surebet:
    st.success(f"✅ ¡SUREBET DETECTADA! Rentabilidad Teórica: {((1/L)-1)*100:.2f}%")
    
    st.markdown("### 📝 Distribución de Apuestas (Redondeo de Seguridad)")
    
    apuestas_redondeadas = []
    for i, cuota in enumerate(cuotas):
        monto_exacto = capital_total / (cuota * L)
        # Redondeo a los 1000 para no levantar sospechas en la casa de apuestas
        redondeado = round(monto_exacto / 1000) * 1000
        apuestas_redondeadas.append(redondeado)
        st.info(f"👉 **Opción {i+1}**: Apostar **${redondeado:,}**")

    inversion_real = sum(apuestas_redondeadas)
    st.markdown("---")
    st.write(f"**Inversión Total Real tras redondeo:** ${inversion_real:,}")

    res_cols = st.columns(num_opciones)
    for i, cuota in enumerate(cuotas):
        retorno = apuestas_redondeadas[i] * cuota
        ganancia = retorno - inversion_real
        perc = (ganancia / inversion_real) * 100
        with res_cols[i]:
            st.metric(f"Si gana Opción {i+1}", f"${retorno:,.0f}", f"{perc:.2f}%")
else:
    st.error("❌ No es una Surebet. El retorno sería negativo.")