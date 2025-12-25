import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from bs4 import BeautifulSoup
import asyncio

# Bot tokenini kiriting
API_TOKEN = '8470507336:AAGQgz0lxGO9Kz8zP1bzeuZFyrKVEVbV0JM'

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Bot va Dispatcher yaratish
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Ma'lumotlar bazasini yaratish
def init_db():
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  dish_name TEXT,
                  ingredients TEXT,
                  instructions TEXT,
                  source TEXT,
                  date_added TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Retseptni bazaga saqlash
def save_recipe(user_id, dish_name, ingredients, instructions, source):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("INSERT INTO recipes (user_id, dish_name, ingredients, instructions, source) VALUES (?, ?, ?, ?, ?)",
              (user_id, dish_name, ingredients, instructions, source))
    conn.commit()
    conn.close()

# Foydalanuvchining barcha retseptlarini olish
def get_user_recipes(user_id):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("SELECT id, dish_name, date_added FROM recipes WHERE user_id = ? ORDER BY date_added DESC", (user_id,))
    recipes = c.fetchall()
    conn.close()
    return recipes

# Retseptni ID bo'yicha olish
def get_recipe_by_id(recipe_id, user_id):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("SELECT dish_name, ingredients, instructions, source FROM recipes WHERE id = ? AND user_id = ?",
              (recipe_id, user_id))
    recipe = c.fetchone()
    conn.close()
    return recipe

# Retseptni o'chirish
def delete_recipe(recipe_id, user_id):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("DELETE FROM recipes WHERE id = ? AND user_id = ?", (recipe_id, user_id))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

# Barcha retseptlarni o'chirish
def delete_all_recipes(user_id):
    conn = sqlite3.connect('recipes.db')
    c = conn.cursor()
    c.execute("DELETE FROM recipes WHERE user_id = ?", (user_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

# Claude API orqali retsept olish
async def search_recipe_claude(dish_name):
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
            }
            
            prompt = f"""Menga "{dish_name}" ovqatining to'liq retseptini o'zbek tilida ber. 
            
Quyidagi formatda javob ber:

OVQAT NOMI: [ovqat nomi]

KERAKLI MASALLIQLAR:
• [masalliq 1]
• [masalliq 2]
• [masalliq 3]
...

TAYYORLASH TARTIBI:
1. [birinchi qadam]
2. [ikkinchi qadam]
3. [uchinchi qadam]
...

Faqat shu formatda javob ber, boshqa hech narsa yozma."""

            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['content'][0]['text']
                    
                    # Javobni parslaymiz
                    lines = content.strip().split('\n')
                    
                    dish_name_final = dish_name
                    ingredients = []
                    instructions = []
                    current_section = None
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith('OVQAT NOMI:'):
                            dish_name_final = line.replace('OVQAT NOMI:', '').strip()
                        elif line.startswith('KERAKLI MASALLIQLAR:'):
                            current_section = 'ingredients'
                        elif line.startswith('TAYYORLASH TARTIBI:'):
                            current_section = 'instructions'
                        elif current_section == 'ingredients' and (line.startswith('•') or line.startswith('-')):
                            ingredients.append(line)
                        elif current_section == 'instructions' and (line[0].isdigit() or line.startswith('•') or line.startswith('-')):
                            instructions.append(line)
                    
                    if ingredients and instructions:
                        return {
                            'name': dish_name_final,
                            'ingredients': '\n'.join(ingredients),
                            'instructions': '\n'.join(instructions),
                            'source': 'Claude AI'
                        }
    except Exception as e:
        logging.error(f"Claude API xatosi: {e}")
    
    return None

# Internetdan o'zbek retseptlari qidirish (yordamchi funksiya)
async def search_recipe_online(dish_name):
    try:
        # Avval Claude API orqali retsept olamiz
        recipe = await search_recipe_claude(dish_name)
        if recipe:
            return recipe
            
        # Agar Claude ishlamasa, oddiy retsept qaytaramiz
        return create_basic_recipe(dish_name)
    except Exception as e:
        logging.error(f"Retsept qidirish xatosi: {e}")
        return create_basic_recipe(dish_name)

# Oddiy retsept yaratish (fallback)
def create_basic_recipe(dish_name):
    basic_recipes = {
        'osh': {
            'name': "O'zbekcha osh",
            'ingredients': '''• 1 kg guruch (devzira yoki boshqa nav)
• 1 kg qo'y go'shti
• 500 g sabzi
• 3-4 dona piyoz
• 200 ml o'simlik yog'i
• 1 bosh sarimsoq
• Zira, barberис, qora murch
• Tuz''',
            'instructions': '''1. Qozonga yog' soling va qizdirib oling
2. Go'shtni mayda bo'laklarga bo'lib, qizarguncha qovuring
3. Piyozni halqa qilib to'g'rab, go'shtga qo'shing
4. Sabzini uzun-uzun qilib kesib, qo'shing
5. Ziravor va tuz qo'shib aralashtiring
6. Suv quyib, 40-50 daqiqa o'rtacha olovda pishiring
7. Guruchni yaxshilab yuvib, go'shtga tekis qilib soling
8. O'rtasiga sarimsoq boshini qo'ying
9. Past olovda 25-30 daqiqa dam tortiring
10. Tayyor oshni aralashtiring va issiq holda dasturxonga torting''',
            'source': 'Milliy retsept'
        },
        'lag\'mon': {
            'name': 'Lag\'mon',
            'ingredients': '''• 500 g xamir (un, tuxum, tuz, suv)
• 300 g mol go'shti
• 2 dona pomidor
• 2 dona piyoz
• 1 dona bolgar qalampiri
• 100 g sabzi
• Ko'katlar (jambil, rayhon)
• Sarimsoq, ziravorlar''',
            'instructions': '''1. Xamirni qo'l bilan cho'zib, lag'mon tayyorlang
2. Go'shtni mayda to'rtburchak qilib kesing
3. Qozonda go'shtni qizarguncha qovuring
4. Piyoz, sabzi, pomidor va qalampirni qo'shing
5. Suv quyib, sous tayyorlang
6. Lag'monni qaynagan suvda 3-4 daqiqa pishiring
7. Pishgan lag'monni likobcha soling
8. Ustidan sous quyib, ko'kat va sarimsoq qo'shing''',
            'source': 'Milliy retsept'
        },
        'somsa': {
            'name': 'Somsa',
            'ingredients': '''• 500 g xamir
• 400 g qo'y go'shti
• 3 dona katta piyoz
• 100 g quyruq yog'i
• Tuz, zira, qora murch
• 1 dona tuxum''',
            'instructions': '''1. Go'sht va piyozni mayda-mayda to'g'rang
2. Quyruq yog'ini kichik kubiklarga kesing
3. Go'sht, piyoz, yog', tuz va ziravor aralashtiring
4. Xamirni yoyib, 10x10 sm kvadratlarga bo'ling
5. Har bir kvadratga nachinka solib, uchburchak yoping
6. Sirt qismiga tuxum surting va zira seping
7. Tandirda yoki duxovkada 180°C da 35-40 daqiqa pishiring''',
            'source': 'Milliy retsept'
        }
    }
    
    dish_lower = dish_name.lower()
    for key in basic_recipes:
        if key in dish_lower:
            return basic_recipes[key]
    
    # Agar topilmasa, umumiy javob
    return {
        'name': dish_name.capitalize(),
        'ingredients': f'''• {dish_name} uchun kerakli masalliqlar
• Internet orqali aniqroq ma'lumot topilmadi
• Iltimos, boshqa ovqat nomi bilan qayta urinib ko'ring''',
        'instructions': '''1. Kechirasiz, bu ovqat uchun to'liq retsept topilmadi
2. Osh, lag'mon, somsa, manti, shashlik kabi mashhur ovqatlarni sinab ko'ring
3. Yoki ovqat nomini aniqroq yozing''',
        'source': 'Lokal malumot'
    }

# States
class RecipeSearch(StatesGroup):
    waiting_for_dish = State()

# Start command
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("🔍 Retsept qidirish"),
        types.KeyboardButton("📚 Mening retseptlarim")
    )
    keyboard.add(
        types.KeyboardButton("🗑 Retsept o'chirish"),
        types.KeyboardButton("❌ Hammasini o'chirish")
    )
    keyboard.add(types.KeyboardButton("🍽 Mashhur ovqatlar"))
    
    await message.answer(
        "🍽 *Oshpaz Bot*ga xush kelibsiz! 👨‍🍳\n\n"
        "Men sizga o'zbek va jahon oshxonasi retseptlari bo'yicha yordam beraman.\n\n"
        "🔍 Retseptlarni qidirish\n"
        "💾 Retseptlarni saqlash\n"
        "📚 Saqlangan retseptlarni ko'rish\n"
        "🗑 Retseptlarni o'chirish\n\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Mashhur ovqatlar
@dp.message_handler(lambda message: message.text == "🍽 Mashhur ovqatlar")
async def show_popular_dishes(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    dishes = [
        "Osh", "Lag'mon", "Somsa", "Manti",
        "Shashlik", "Mastava", "Dimlama", "Norin",
        "Chuchvara", "Qozonkabob", "Tandir kabob", "Shorva"
    ]
    
    for i in range(0, len(dishes), 2):
        if i + 1 < len(dishes):
            keyboard.add(
                types.KeyboardButton(dishes[i]),
                types.KeyboardButton(dishes[i + 1])
            )
        else:
            keyboard.add(types.KeyboardButton(dishes[i]))
    
    keyboard.add(types.KeyboardButton("🏠 Asosiy menyu"))
    
    await message.answer(
        "🍽 *Mashhur o'zbek ovqatlari:*\n\n"
        "Qaysi ovqatning retseptini ko'rishni xohlaysiz?\n"
        "Ovqat nomini tanlang yoki o'zingiz yozing:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Asosiy menyuga qaytish
@dp.message_handler(lambda message: message.text == "🏠 Asosiy menyu")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.finish()
    await send_welcome(message)

# Retsept qidirish
@dp.message_handler(lambda message: message.text == "🔍 Retsept qidirish")
async def search_dish(message: types.Message):
    await message.answer(
        "🔍 Qaysi ovqatning retseptini qidirishni xohlaysiz?\n\n"
        "Ovqat nomini *o'zbek tilida* yozing:\n"
        "Masalan: osh, lag'mon, somsa, manti, shashlik, dimlama va h.k.\n\n"
        "Yoki 🍽 Mashhur ovqatlar tugmasini bosing.",
        parse_mode="Markdown"
    )
    await RecipeSearch.waiting_for_dish.set()

# Internetdan retsept qidirish va saqlash
@dp.message_handler(state=RecipeSearch.waiting_for_dish)
async def find_and_save_recipe(message: types.Message, state: FSMContext):
    dish_name = message.text.strip()
    
    loading_msg = await message.answer("⏳ Retsept qidirilmoqda, biroz kuting...")
    
    recipe = await search_recipe_online(dish_name)
    
    await loading_msg.delete()
    
    if recipe:
        # Retseptni bazaga saqlash
        save_recipe(
            message.from_user.id,
            recipe['name'],
            recipe['ingredients'],
            recipe['instructions'],
            recipe['source']
        )
        
        # Retseptni ko'rsatish
        response = (
            f"✅ *{recipe['name']}*\n\n"
            f"*📝 Kerakli masalliqlar:*\n{recipe['ingredients']}\n\n"
            f"*👨‍🍳 Tayyorlash tartibi:*\n{recipe['instructions']}\n\n"
            f"💾 Retsept bazaga saqlandi!\n"
            f"📍 Manba: {recipe['source']}"
        )
        
        await message.answer(response, parse_mode="Markdown")
    else:
        await message.answer(
            f"❌ Kechirasiz, '{dish_name}' uchun retsept topilmadi.\n\n"
            "Boshqa ovqat nomi bilan qayta urinib ko'ring.\n"
            "Masalan: osh, lag'mon, somsa, manti, shashlik"
        )
    
    await state.finish()

# Mashhur ovqatlar ro'yxatidan tanlash
@dp.message_handler(lambda message: message.text in [
    "Osh", "Lag'mon", "Somsa", "Manti", "Shashlik", 
    "Mastava", "Dimlama", "Norin", "Chuchvara", 
    "Qozonkabob", "Tandir kabob", "Shorva"
])
async def quick_recipe_search(message: types.Message):
    dish_name = message.text
    
    loading_msg = await message.answer("⏳ Retsept tayyorlanmoqda...")
    
    recipe = await search_recipe_online(dish_name)
    
    await loading_msg.delete()
    
    if recipe:
        save_recipe(
            message.from_user.id,
            recipe['name'],
            recipe['ingredients'],
            recipe['instructions'],
            recipe['source']
        )
        
        response = (
            f"✅ *{recipe['name']}*\n\n"
            f"*📝 Kerakli masalliqlar:*\n{recipe['ingredients']}\n\n"
            f"*👨‍🍳 Tayyorlash tartibi:*\n{recipe['instructions']}\n\n"
            f"💾 Retsept bazaga saqlandi!\n"
            f"📍 Manba: {recipe['source']}"
        )
        
        await message.answer(response, parse_mode="Markdown")

# Saqlangan retseptlarni ko'rsatish
@dp.message_handler(lambda message: message.text == "📚 Mening retseptlarim")
async def show_saved_recipes(message: types.Message):
    recipes = get_user_recipes(message.from_user.id)
    
    if not recipes:
        await message.answer(
            "📭 Sizda hali saqlangan retseptlar yo'q.\n\n"
            "🔍 Retsept qidirish tugmasini bosing va biror retsept qidiring!"
        )
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for recipe_id, dish_name, date_added in recipes:
        keyboard.add(
            types.InlineKeyboardButton(
                text=f"📖 {dish_name} ({date_added[:10]})",
                callback_data=f"recipe_{recipe_id}"
            )
        )
    
    await message.answer(
        f"📚 *Saqlangan retseptlarim* ({len(recipes)} ta)\n\n"
        "Ko'rish uchun tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Tanlangan retseptni ko'rsatish
@dp.callback_query_handler(lambda c: c.data.startswith('recipe_'))
async def show_recipe_detail(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split('_')[1])
    recipe = get_recipe_by_id(recipe_id, callback.from_user.id)
    
    if recipe:
        dish_name, ingredients, instructions, source = recipe
        
        response = (
            f"🍽 *{dish_name}*\n\n"
            f"*📝 Kerakli masalliqlar:*\n{ingredients}\n\n"
            f"*👨‍🍳 Tayyorlash tartibi:*\n{instructions}\n\n"
            f"📍 Manba: {source}"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                text="🗑 Bu retseptni o'chirish",
                callback_data=f"delete_{recipe_id}"
            )
        )
        
        await callback.message.answer(response, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await callback.answer("❌ Retsept topilmadi", show_alert=True)

# Bitta retseptni o'chirish (tugma orqali)
@dp.message_handler(lambda message: message.text == "🗑 Retsept o'chirish")
async def delete_recipe_start(message: types.Message):
    recipes = get_user_recipes(message.from_user.id)
    
    if not recipes:
        await message.answer("📭 Sizda o'chiriladigan retseptlar yo'q.")
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for recipe_id, dish_name, date_added in recipes:
        keyboard.add(
            types.InlineKeyboardButton(
                text=f"🗑 {dish_name}",
                callback_data=f"delete_{recipe_id}"
            )
        )
    
    await message.answer(
        "🗑 *Qaysi retseptni o'chirmoqchisiz?*\n\n"
        "Tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Retseptni o'chirish (callback)
@dp.callback_query_handler(lambda c: c.data.startswith('delete_'))
async def confirm_delete_recipe(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split('_')[1])
    
    if delete_recipe(recipe_id, callback.from_user.id):
        await callback.answer("✅ Retsept o'chirildi!", show_alert=True)
        await callback.message.edit_text("✅ Retsept muvaffaqiyatli o'chirildi!")
    else:
        await callback.answer("❌ Xato yuz berdi", show_alert=True)

# Barcha retseptlarni o'chirish
@dp.message_handler(lambda message: message.text == "❌ Hammasini o'chirish")
async def delete_all_confirm(message: types.Message):
    recipes = get_user_recipes(message.from_user.id)
    
    if not recipes:
        await message.answer("📭 Sizda o'chiriladigan retseptlar yo'q.")
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Ha, hammasini o'chirish", callback_data="delete_all_yes"),
        types.InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="delete_all_no")
    )
    
    await message.answer(
        f"⚠️ *Diqqat!*\n\n"
        f"Siz {len(recipes)} ta saqlangan retseptni o'chirmoqchisiz.\n"
        f"Bu amalni ortga qaytarib bo'lmaydi!\n\n"
        f"Davom etishni xohlaysizmi?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Barcha retseptlarni o'chirishni tasdiqlash
@dp.callback_query_handler(lambda c: c.data == 'delete_all_yes')
async def delete_all_confirmed(callback: types.CallbackQuery):
    try:
        deleted = delete_all_recipes(callback.from_user.id)
        await callback.message.edit_text(
            f"✅ {deleted} ta retsept o'chirildi!\n\n"
            "🔍 Yangi retseptlar qidirish uchun tegishli tugmani bosing."
        )
        await callback.answer("Retseptlar o'chirildi!", show_alert=False)
    except Exception as e:
        logging.error(f"O'chirishda xatolik: {e}")
        await callback.answer("❌ Xatolik yuz berdi!", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'delete_all_no')
async def delete_all_cancelled(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text("❌ Bekor qilindi. Retseptlar saqlanib qoldi.")
        await callback.answer()
    except Exception as e:
        await callback.answer("Bekor qilindi", show_alert=False)

# Botni ishga tushirish
if __name__ == '__main__':
    init_db()
    print("✅ Bot ishga tushdi...")
    print("📝 O'zbek tilida retseptlar qidirish tayyor!")
    executor.start_polling(dp, skip_updates=True)