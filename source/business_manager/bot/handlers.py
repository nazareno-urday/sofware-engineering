# ============================================================
# IMPORTACIONES
# ============================================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)


# ============================================================
# CONFIGURACIÓN DEL BOT
# ============================================================

TOKEN = "8906729346:AAF_E7qruMduqaS3OlVNQFEYYdoaasaSAuI"


# ============================================================
# MÓDULO 1 - INICIAR BOT
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    botones = [
        [
            InlineKeyboardButton(
                "✅ Sí",
                callback_data="iniciar_si"
            ),
            InlineKeyboardButton(
                "❌ No",
                callback_data="iniciar_no"
            )
        ]
    ]

    teclado = InlineKeyboardMarkup(botones)

    await update.message.reply_text(
        "🌅 ¿Iniciar día?",
        reply_markup=teclado
    )


# ============================================================
# MÓDULO 2 - RESPUESTA INICIAR DÍA
# ============================================================

async def respuesta_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    # --------------------------------------------------------
    # SI EL USUARIO QUIERE INICIAR EL DÍA
    # --------------------------------------------------------

    if query.data == "iniciar_si":

        await query.edit_message_text(
            "✅ Día iniciado"
        )

        # Después de iniciar el día preguntamos por el historial

        await preguntar_historial(query, context)


    # --------------------------------------------------------
    # SI EL USUARIO NO QUIERE INICIAR EL DÍA
    # --------------------------------------------------------

    elif query.data == "iniciar_no":

        await query.edit_message_text(
            "❌ Día no iniciado"
        )


# ============================================================
# MÓDULO 3 - PREGUNTAR SI QUIERE VER EL HISTORIAL
# ============================================================

async def preguntar_historial(query, context):

    botones = [
        [
            InlineKeyboardButton(
                "✅ Sí",
                callback_data="historial_si"
            ),
            InlineKeyboardButton(
                "❌ No",
                callback_data="historial_no"
            )
        ]
    ]

    teclado = InlineKeyboardMarkup(botones)

    await query.message.reply_text(
        "📋 ¿Mostrar historial?",
        reply_markup=teclado
    )


# ============================================================
# MÓDULO 4 - RESPUESTA DEL HISTORIAL
# ============================================================

async def respuesta_historial(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()


    # --------------------------------------------------------
    # MOSTRAR HISTORIAL
    # --------------------------------------------------------

    if query.data == "historial_si":

        await query.edit_message_text(
            "📋 Mostrando historial..."
        )


    # --------------------------------------------------------
    # NO MOSTRAR HISTORIAL
    # --------------------------------------------------------

    elif query.data == "historial_no":

        await query.edit_message_text(
            "❌ Historial no mostrado"
        )


# ============================================================
# MÓDULO 5 - CREACIÓN DE LA APLICACIÓN
# ============================================================

app = Application.builder().token(TOKEN).build()


# ============================================================
# MÓDULO 6 - HANDLERS
# ============================================================

# Detecta el comando /start
app.add_handler(
    CommandHandler(
        "start",
        start
    )
)


# Detecta los botones relacionados con iniciar el día
app.add_handler(
    CallbackQueryHandler(
        respuesta_inicio,
        pattern="^iniciar_"
    )
)


# Detecta los botones relacionados con el historial
app.add_handler(
    CallbackQueryHandler(
        respuesta_historial,
        pattern="^historial_"
    )
)



# ============================================================
# MÓDULO 7 - EJECUCIÓN DEL BOT
# ============================================================

print("Bot iniciado...")

app.run_polling()