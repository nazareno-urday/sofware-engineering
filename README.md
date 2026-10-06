# Business Manager

Proyecto de Ingeniería de Software 2 para un negocio de ferias.
El bot de Telegram permite manejar la jornada y consultar reportes.
Los productos y los importes se cargan en Google Sheets.

A las 00:00 de Argentina, el programa guarda las ventas, los egresos
y el resumen del día. Después vacía los movimientos diarios y manda
el resumen al chat que tocó **Comenzar el día**.

## Instalación

Se usa Python 3.12 y uv. Desde la raíz del proyecto:

```powershell
uv sync --locked --extra dev --python 3.12
```

Si todavía no existe .env, crearlo con:

```powershell
Copy-Item .env.example .env
```

Completar estas variables en .env:

| Variable | Qué contiene |
| --- | --- |
| TELEGRAM_BOT_TOKEN | Token del bot creado con BotFather |
| ALLOWED_USER_IDS | IDs de las personas autorizadas, separados por comas |
| GOOGLE_SHEET_ID | ID de la spreadsheet |
| GOOGLE_CREDENTIALS_FILE | Ruta del JSON de Google; por defecto credentials.json |
| STATE_DIR | Carpeta del estado guardado; por defecto .state |
| CLOSE_TIME | Hora argentina del cierre; dejar 00:00 |

Las rutas relativas se toman desde la raíz del proyecto.
Si una variable ya está definida en el entorno, tiene prioridad sobre .env.
Después de cambiar la configuración hay que reiniciar el bot.
.env, credentials.json y .state están ignorados por Git.
Si se cambian sus nombres, también hay que agregar los nuevos al .gitignore.

### Telegram

Crear el bot en @BotFather con /newbot y guardar su token en .env.
El token identifica al bot. ALLOWED_USER_IDS indica quién puede usarlo.

Para conocer un ID, poner temporalmente ALLOWED_USER_IDS=1,
arrancar el bot y mandarle /id por privado. Después reemplazar el 1
por el ID recibido y reiniciar. Si lo usan dos personas, separar sus IDs
con una coma. /id solo muestra el número de quien escribe.

Las acciones del negocio funcionan en chats privados y para los IDs
autorizados. Otro usuario no puede cambiar el dueño de una jornada activa.
[Instrucciones de BotFather](https://core.telegram.org/bots/tutorial).

### Google

1. Habilitar Google Sheets API en el proyecto de Google Cloud.
2. Crear una service account y descargar su clave JSON.
3. Guardarla como credentials.json en la raíz del proyecto.
4. Compartir la spreadsheet con el correo de esa cuenta como **Editor**.
5. Compartirla también con la persona que va a cargar los movimientos.

La clave de Google y el token de Telegram son distintos.
No hay que subir ninguno a Git ni pegarlos en el chat.

El acceso usa el scope https://www.googleapis.com/auth/spreadsheets.
google-auth se ocupa de renovar el token de Google.
Las credenciales se leen cuando se hace la primera consulta, no al importar
el módulo. Por eso los tests se pueden ejecutar sin secretos.

Guías de Google: [crear una cuenta](https://docs.cloud.google.com/iam/docs/service-accounts-create)
y [descargar una clave](https://docs.cloud.google.com/iam/docs/keys-create-delete).

## Hoja de cálculo

Se usan exactamente estas cuatro pestañas:

| Pestaña | Encabezados |
| --- | --- |
| Ingresos, A1:C1 | Producto, Mercado Pago, Efectivo |
| Egresos, A1:C1 | Egreso, Mercado Pago, Efectivo |
| Historial, A1:E1 | Fecha, Total, Total Mercado Pago, Total efectivo, Total egresos |
| Registro ingresos, A1:D1 | Fecha, Producto, Mercado Pago, Efectivo |
| Registro ingresos, F1:I1 | Fecha, Egreso, Mercado Pago, Efectivo |

Registro ingresos tiene dos bloques: ventas en A:D y egresos en F:I.
La columna E queda vacía. Si F1:I1 todavía está vacío, seleccionar F1
y pegar esta línea con tabulaciones:

```text
Fecha	Egreso	Mercado Pago	Efectivo
```

Si ya hay datos o encabezados distintos, revisarlos antes de cambiarlos.
El programa comprueba los títulos, pero no los reemplaza.

Los movimientos diarios van en Ingresos!A2:C500 y Egresos!A2:C500.
No cargar fuera de esos rangos. Historial y Registro ingresos se conservan
y se leen completos, aunque tengan más de 500 filas.
Los dos bloques del registro pueden tener distinta cantidad de filas.

Cada movimiento necesita un concepto y al menos un importe.
Se puede pagar por MP, efectivo o ambos; una fila de ingreso cuenta
como una venta. Un medio vacío vale cero y los importes cero son válidos.
Se rechazan negativos y datos incompletos o inválidos antes de archivar.
No se manejan devoluciones en esta versión.

Escribir los importes como números de Sheets, no como texto con símbolos
de moneda. El programa los lee sin formato regional.
Se usa float y round a dos decimales. Algunos decimales no se representan
exactamente en float, por eso también se redondean los totales.
Total en Historial es ingreso bruto. Los saldos del resumen son ingresos
menos egresos del día, sin incluir dinero que ya había en la caja o cuenta.

## Ejecutar

```powershell
uv run --no-sync business-manager
```

También funciona uv run --no-sync -m business_manager.main.
En PyCharm, ejecutar el módulo business_manager.main con .venv
y la raíz del proyecto como directorio de trabajo.
No ejecutar main.py como archivo suelto.

El programa queda abierto haciendo polling. Ctrl+C lo detiene.
La PC tiene que estar encendida, conectada y sin suspensión.
No hace falta abrir un puerto ni usar un servidor externo.
La zona horaria es America/Argentina/Buenos_Aires;
tzdata permite usarla también en Windows.

Para iniciarlo con el Programador de tareas de Windows:

- Programa: ruta absoluta a .venv/Scripts/pythonw.exe.
- Argumentos: -m business_manager.main.
- Iniciar en: ruta absoluta de la raíz del proyecto.
- Disparador: al iniciar sesión.
- Activar el reinicio si falla y elegir "No iniciar una nueva instancia".
- Quitar el límite de tiempo que detiene la tarea y revisar las
  condiciones de batería y suspensión.

Durante las pruebas conviene usar la terminal para ver los errores.
La tarea debe ejecutar el proceso completo y mantenerlo abierto.
Usar un solo proceso y una sola carpeta de estado para el negocio.

## Menú

| Botón | Acción |
| --- | --- |
| Comenzar el día | Guarda fecha y destinatario; envía el enlace a Sheets |
| Ver resumen | Lee los movimientos actuales sin guardarlos ni borrarlos |
| Imprimir historial | Envía un PDF de las jornadas cerradas |
| Imprimir ventas | Envía un PDF del detalle de ventas |
| Imprimir egresos | Envía un PDF del detalle de gastos |
| Cerrar día | Pide confirmación y ejecuta el cierre |
| Recuperación | Permite registrar una fecha pendiente o revisar una limpieza |

Escribir hola o mandar una foto muestra el menú.
El texto libre no se interpreta como una venta.

Para imprimir se puede elegir Todo, Hoy o un rango:
DD/MM/AAAA - DD/MM/AAAA. Volver cancela la selección.
Hoy puede estar vacío si la jornada todavía no está cerrada.
Los PDFs son A4, incluyen totales y repiten los encabezados en cada página.

Comenzar el día dos veces mantiene la misma jornada.
Hay un solo negocio y una jornada por fecha.
Si se cierra antes de medianoche, no se abre otra jornada con esa misma fecha.
La hoja queda libre para el día siguiente.

## Cómo se organiza el código

Todo el paquete está en source/business_manager/.

| Archivo | Responsabilidad |
| --- | --- |
| config.py | Lee y valida .env |
| main.py | Arma la aplicación, los handlers y las tareas programadas |
| bot/handlers.py | Decide qué hacer con cada botón o mensaje |
| jobs/close_day.py | Ejecuta el cierre automático y manda avisos |
| services/calculations.py | Valida filas y calcula importes |
| services/sheets.py | Hace las consultas y escrituras a Google Sheets |
| services/day_closure.py | Coordina el cierre y guarda su avance |
| services/reports.py | Arma el texto del resumen y los PDFs |

Por ejemplo, Ver resumen llama a preview() en day_closure.py.
Esa función lee ambas hojas con read_daily() y pasa las filas
a calculate_day(). El resultado es un diccionario de totales;
summary_text() lo convierte en el mensaje que recibe el usuario.

sum_payments() recorre filas ya validadas y suma las columnas MP y efectivo.
normalize_rows() completa las celdas que Google no devuelve cuando están
vacías. Así un importe en efectivo no termina contado como MP.

send_report() se ocupa de elegir el período, leer el registro
y mandar el PDF. generate_pdf() recibe filas y devuelve el documento
en memoria, sin modificar la spreadsheet.

El cierre manual y el automático llaman al mismo close().
_prepare_day() prepara las filas y guarda dónde van a archivarse.
close() continúa con el archivo, la verificación y la limpieza.
Las llamadas lentas a Google se ejecutan con asyncio.to_thread()
para que no ocupen el event loop de Telegram.

## Cierre y recuperación

.state/journal.json guarda la jornada, su dueño, una copia de los movimientos
(snapshot), los rangos del archivo y si falta enviar el aviso.
No borrar este archivo para reintentar un cierre. Conviene respaldarlo:
contiene datos del negocio, aunque no guarda tokens ni claves.

El cierre sigue estos pasos:

1. Comprueba la jornada y evita dos cierres al mismo tiempo.
2. Lee y valida Ingresos y Egresos.
3. Guarda el snapshot y reserva los rangos de destino en el JSON.
4. Escribe ventas, egresos e historial y comprueba sus valores.
5. Compara las hojas diarias con el snapshot.
6. Limpia solo los valores de las filas archivadas.
7. Guarda el cierre y envía el resumen al dueño de la jornada.

El JSON se escribe en un archivo aparte y después reemplaza al anterior.
Las fases guardadas son active, prepared, archived, clearing y closed.
Permiten saber hasta dónde llegó el cierre si se interrumpió.

Si falla una escritura, se consultan los mismos rangos al reintentar.
No se usa append otra vez sin comprobar qué quedó guardado.
Si cambiaron los movimientos diarios, el programa se detiene antes de limpiar.
Hay que respaldar y separar los nuevos movimientos, restaurar el snapshot
original y volver a usar Cerrar día.

Si el proceso estaba apagado o suspendido a medianoche,
al arrancar o en la revisión de cada 60 segundos avisa que quedó una jornada
pendiente. No cierra automáticamente al arrancar. Revisar si se mezclaron
movimientos de distintas fechas y cerrar la jornada pendiente desde el menú.
Las filas diarias no tienen fecha, así que el programa no puede separarlas.
Un cierre programado que llega más de un segundo tarde se deja para revisión.

Si hay movimientos pero no se inició ninguna jornada, usar Recuperación
y Registrar jornada pendiente con la fecha real. Después cerrar.
Comenzar el día los asignaría a la fecha actual.

Si la fase quedó en **clearing**, la limpieza pudo ejecutarse aunque no haya
llegado la respuesta:

1. Revisar snapshot, payloads, destinations y clear_ranges en el JSON.
2. Comprobar que los archivos permanentes conservan la jornada.
3. Si las posiciones diarias indicadas están vacías, dejarlas así.
   Si quedan valores, respaldar y separar cualquier movimiento nuevo.
   Borrar manualmente solo los valores antiguos que se reconocen como
   archivados. Ante una duda, conservarlos y detenerse.
4. Usar Recuperación y Confirmar limpieza revisada. El programa comprueba
   el archivo y los vacíos, y termina sin repetir la limpieza.
5. Cargar los movimientos nuevos separados en la jornada que corresponda.

Si falla Telegram, el aviso queda pendiente y se reintenta cada 60 segundos
y al reiniciar. Esto no vuelve a archivar ni limpiar.
Una respuesta perdida de Telegram puede hacer que el aviso llegue dos veces.

El lock del programa no bloquea a quien edita Sheets.
Todavía existe un intervalo entre la última lectura y la limpieza
en el que una edición humana puede perderse. No editar durante el cierre.
Google no ofrece una transacción para todo este proceso; también hay que
evitar otros programas que escriban en los mismos registros.

## Pruebas

Los tests usan Google y Telegram simulados; no necesitan .env ni credenciales.

```powershell
uv run --no-sync black .
uv run --no-sync ruff check .
uv run --no-sync black --check .
uv run --no-sync mypy source
uv run --no-sync bandit -c pyproject.toml -r source
uv run --no-sync pytest --cov=source --cov-report=term-missing
```

La CI ejecuta estos controles con Python 3.12.
Hay pruebas de cálculos, escrituras parciales, reinicios, concurrencia,
destinatarios, menús y PDFs de más de 500 filas.
Pasar estos tests no confirma los permisos de las cuentas reales.

### Prueba desde Telegram

Usar una copia de la spreadsheet y un bot de prueba,
con STATE_DIR=.state-test, para no mezclar pruebas con ventas reales.
Compartir también la copia con la service account.
Respaldar los datos de prueba que ya existan antes de limpiarlos manualmente.

1. Tocar Comenzar el día y comprobar la fecha y el enlace.
2. Cargar en Ingresos: laureano / 1000 / 2000 y comida / 8000 / 7000.
   En Egresos: coca / 2000 / 900.
3. Ver resumen debe mostrar ingresos MP 9000, efectivo 9000, bruto 18000
   y dos ventas. Egresos: 2900. Saldos: MP 7000, efectivo 8100, total 15100.
4. Cerrar día y confirmar, sin editar mientras se procesa.
5. Comprobar dos ventas en A:D, un egreso en F:I y una fila de Historial,
   con la fecha de la jornada. Las hojas diarias deben quedar vacías,
   conservando encabezados y formato.
6. Comprobar el mensaje en el chat que inició la jornada y abrir los PDFs.
   Repetir Cerrar día no debe agregar registros.
7. Al día siguiente, comenzar otra jornada y cargar una venta.
   Para probar esa transición sin esperar, registrar primero ayer desde
   Recuperación en una copia vacía; cerrarlo y después comenzar hoy.

Para probar el horario automático, detener el bot real y usar la copia
y el bot de prueba. Poner CLOSE_TIME a dos o tres minutos de la hora argentina
actual, dentro del mismo día. Reiniciar, comenzar el día y cargar los datos.
Esperar el cierre sin tocar el botón manual.
Fuera de 00:00, este ensayo cierra la fecha actual.

Al terminar, detener el bot de prueba y restaurar CLOSE_TIME=00:00,
el ID de la hoja real, el token original y STATE_DIR=.state.
No reemplazar el estado real con el de pruebas.
