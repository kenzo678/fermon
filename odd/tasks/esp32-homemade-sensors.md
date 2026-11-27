# Feature: esp32-homemade-sensors

> Estado: **planificado, sin iniciar** (2026-11-25). Sensores decididos y lista de compra cerrada
> (2026-11-26); falta comprarlos. Antes de empezar, revisar este plan con el usuario.

## Objetivo
Primera prueba con hardware casero: reemplazar el simulador por sensores reales conectados a un ESP32,
sin cambiar el backend, y demostrar el flujo completo de la tesis con mediciones físicas.

## Material disponible
ESP32, Arduino Nano, dos pantallas OLED I2C (3.3–5 V; probablemente SSD1306 128×64, dirección 0x3C).
Ninguno mide nada: faltan los sensores.

## Lista de compra
Tienda de referencia: EC Robotics (Bolivia), con precio estudiantil presentando el carnet. Precios
vistos el 2026-11-26.

### Sensores (decididos)
| Cant. | Componente | Precio | Para qué | Notas |
| --- | --- | --- | --- | --- |
| 2 | Sensor DS18B20 Sumergible (funda de acero) | 25 Bs c/u | Temperatura del líquido | Digital 1-Wire, ±0.5 °C, 3.3 V. Uno de repuesto o para un segundo tanque |
| 1 | Sensor de presión MPX5999D | 180 Bs (estudiantil) | Presión del espacio de cabeza (CO₂) | 0–1000 kPa, salida 0.2–4.7 V, 5 V → va al Nano. Sin rosca ni pico: hay que adaptar el montaje. Error ±2.5 % FS (~±0.25 bar): se compensa con calibración en dos puntos. **Solo gas, nunca líquido** |
| 1 | Módulo MPU6050 | — | Solo F5 (hidrómetro → densidad → alcohol) | Opcional |
| (1) | Módulo DS18B20 | 25 Bs | Adaptador | Solo si trae bornera para el sensor sumergible (incluye el pull-up). Si trae el sensor soldado, no hace falta |

Descartados: BMP280/BMP180/BME280 (presión del aire ambiente, no del tanque), DHT/SHT (aire),
LM35/TMP36/NTC (no sumergibles, analógicos), termocupla K/MAX6675 (para altas temperaturas, ±2 °C),
MLX90614 (infrarrojo, superficie), MQ-3 (vapor en el aire, no % del líquido), YF-S201 (caudal) y
sensores de fuerza. Alternativa preferible para presión si se puede importar: HK1100C (rosca G1/4,
0.5–4.5 V); el plan F2 sirve igual para ambos. No hace falta RTC (DS3231): el ESP32 toma la hora por NTP
y la mantiene sin WiFi.

### Componentes genéricos
| Cant. | Componente | Para qué |
| --- | --- | --- |
| 1 | Kit surtido de resistencias (incluye 4.7 kΩ y 10 kΩ) | Pull-up del DS18B20; divisor de tensión si falta el conversor de nivel |
| 1 | Protoboard de 830 puntos | Armado sin soldar |
| 1 | Juego de cables jumper macho-macho | Protoboard |
| 1 | Juego de cables jumper macho-hembra | Pines del ESP32, Nano y OLED a la protoboard |
| 1 | Conversor de nivel lógico 3.3 V ↔ 5 V bidireccional (4 canales) | Enlace serie Nano (5 V) ↔ ESP32 (3.3 V) |
| 1 | Cable USB con datos para el ESP32 (micro-USB o USB-C, según la placa) | Programar y alimentar |
| 1 | Cable mini-USB con datos para el Nano | Programar y alimentar |
| 1 | Fuente 5 V / 2 A (sirve un cargador de celular) | Funcionar sin la PC |
| 1 | Tira de pines macho (headers) | Por si el ESP32, el Nano o las OLED vienen sin soldar |
| 1 | Bornera de 3 vías o terminales | Conexión firme del DS18B20 si no hay módulo adaptador |

### Ferretería / montaje (presión)
| Cant. | Componente | Para qué |
| --- | --- | --- |
| 1 | Conector neumático o pico para manguera de 4–6 mm | Acople sobre el orificio del MPX5999D |
| 1 | Epoxi de dos componentes (Poxipol o similar) | Pegar y sellar el acople sin tapar el orificio |
| 1 m | Manguera de 4–6 mm (silicona o PU) | Del sensor a la parte superior del fermentador |
| 1 | Manómetro de referencia (de neumáticos o de compresor) | Segundo punto de calibración (1–2 bar) |
| — | Agua jabonosa | Probar estanqueidad |

### Opcional
- Caja plástica estanca (tipo IP65) para la electrónica cerca del fermentador.
- Multímetro, si no hay: calibración y diagnóstico.
- Solo F5 (hidrómetro): batería 18650, porta-pilas, módulo cargador TP4056 y un tubo PET estanco
  ("preforma") que flote.

## Contrato que debe cumplir el dispositivo (ya existe, el backend no cambia)
- Tópico MQTT `fermon/tanks/{tank_id}/readings`, QoS 1.
- Payload JSON `{"sensor_id", "measurement", "value", "unit", "recorded_at"}`.
- Unidades y rangos: `temperature`/`celsius` (−20..100), `pressure`/`bar` (0..10), `alcohol`/`percent_abv` (0..20).
- `recorded_at` en ISO 8601 UTC con zona: el ESP32 debe sincronizar hora por NTP antes de publicar.
- El tanque se registra solo con la primera lectura; luego se renombra desde la UI (admin).
- Alternativa HTTP: `POST /readings` con `X-Device-Key` (`DEVICE_API_KEYS`).
- Referencia exacta del formato: el simulador (`simulator/`).

## Rol de cada placa
- **ESP32**: nodo principal (WiFi). Lee el DS18B20, publica por MQTT, OLED con temperatura, presión,
  estado WiFi/MQTT y último envío.
- **Arduino Nano**: su ADC es de 5 V, así que lee el MPX5999D (0.2–4.7 V) directo; el ESP32 no tolera
  más de 3.3 V y su ADC es poco lineal. Envía el valor al ESP32 por UART: la línea TX del Nano (5 V)
  necesita divisor resistivo o level shifter antes del RX del ESP32. Segunda OLED con la presión local.
- **OLED**: si comparten el mismo bus I2C, una debe pasar a 0x3D (puente de soldadura). En placas
  separadas no hay conflicto.

## Fases
- [ ] F1 — Banco con temperatura: ESP32 + DS18B20 + OLED. WiFi, NTP, MQTT QoS 1 (ojo: `PubSubClient`
  solo publica QoS 0; usar `esp-mqtt`/`AsyncMqttClient`), reconexión y buffer en RAM si se cae la red.
  Firmware con PlatformIO en `firmware/esp32-node/`, credenciales en un archivo ignorado por git.
  Validación: la lectura aparece en el dashboard como un tanque nuevo (p. ej. `tank-esp32`).
- [ ] F2 — Presión: Nano + MPX5999D + OLED, enlace serie con el ESP32. Montaje con acople y manguera
  en la parte superior del fermentador (solo gas). Calibración en dos puntos: cero al aire libre y un
  punto de 1–2 bar contra el manómetro de referencia.
- [ ] F3 — Prueba de punta a punta: renombrar el tanque, lote con rango y perfil, calentar el sensor con
  agua tibia → alerta fuera de rango, desconectar → alerta de sensor callado, finalizar → reporte PDF.
- [ ] F4 — Hacia la cervecería: usuario/contraseña MQTT por dispositivo con ACL por tópico (hoy el
  broker es anónimo); luego TLS.
- [ ] F5 (opcional) — Densidad: hidrómetro flotante tipo iSpindel (ESP32 + acelerómetro) → densidad →
  ABV. Probablemente conviene agregar una medición `gravity` en el backend y calcular el ABV allí.

## Pendientes del entorno
- El puerto 1883 ya está publicado en `docker-compose.yml`; el firewall del host puede bloquearlo para la
  red local (revisar al empezar F1).
- Decidir si `firmware/` se compila en Docker (PlatformIO) para mantener la regla de "nada instalado en el
  host"; el flasheo por USB sí requiere acceso al dispositivo desde el host.

## Restricciones
Las mismas del proyecto (ver `AGENTS.md`): ODD, Strict TDD donde aplique (lógica de firmware testeable
en nativo con PlatformIO `native`), Conventional Commits, código en inglés y planificación en español.
