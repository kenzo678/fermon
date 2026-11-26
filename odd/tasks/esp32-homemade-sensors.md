# Feature: esp32-homemade-sensors

> Estado: **planificado, sin iniciar** (2026-11-25). Falta conseguir los sensores. Antes de empezar,
> confirmar con el usuario qué sensores hay y revisar este plan.

## Objetivo
Primera prueba con hardware casero: reemplazar el simulador por sensores reales conectados a un ESP32,
sin cambiar el backend, y demostrar el flujo completo de la tesis con mediciones físicas.

## Material disponible
ESP32, Arduino Nano, dos pantallas OLED I2C (3.3–5 V; probablemente SSD1306 128×64, dirección 0x3C).
Ninguno mide nada: faltan los sensores.

## Sensores a conseguir
| Medición | Sensor | Notas |
| --- | --- | --- |
| Temperatura | DS18B20 sumergible (funda de acero) + resistencia 4.7 kΩ (pull-up) | Digital (1-Wire), ±0.5 °C, funciona a 3.3 V |
| Presión | Transductor 0–5 bar, salida 0.5–4.5 V, rosca G1/4 | El tipo usado en fermentadores a presión |
| Alcohol | Sin sensor por ahora (sigue simulado) | El MQ-3 mide vapor en el aire, no el % del líquido: no sirve. Lo real es medir densidad (ver F5) |

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
- **Arduino Nano**: su ADC es de 5 V, así que lee el transductor (0.5–4.5 V) directo; el ESP32 no tolera
  más de 3.3 V y su ADC es poco lineal. Envía el valor al ESP32 por UART: la línea TX del Nano (5 V)
  necesita divisor resistivo o level shifter antes del RX del ESP32. Segunda OLED con la presión local.
- **OLED**: si comparten el mismo bus I2C, una debe pasar a 0x3D (puente de soldadura). En placas
  separadas no hay conflicto.

## Fases
- [ ] F1 — Banco con temperatura: ESP32 + DS18B20 + OLED. WiFi, NTP, MQTT QoS 1 (ojo: `PubSubClient`
  solo publica QoS 0; usar `esp-mqtt`/`AsyncMqttClient`), reconexión y buffer en RAM si se cae la red.
  Firmware con PlatformIO en `firmware/esp32-node/`, credenciales en un archivo ignorado por git.
  Validación: la lectura aparece en el dashboard como un tanque nuevo (p. ej. `tank-esp32`).
- [ ] F2 — Presión: Nano + transductor + OLED, enlace serie con el ESP32, calibración del cero
  (0.5 V = 0 bar). Validación contra un manómetro si hay uno.
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
