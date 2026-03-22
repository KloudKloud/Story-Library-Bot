import asyncio

class StartupManager:

    def __init__(self):
        self.add_worker_started = False
        self.auto_update_started = False

    async def start_add_worker(self, bot, add_worker):

        if not self.add_worker_started:
            bot.loop.create_task(add_worker())
            self.add_worker_started = True
            print("📚 Add worker started.")

    async def start_auto_update(self, bot, auto_update_loop):

        if not self.auto_update_started:
            bot.loop.create_task(auto_update_loop(bot, initial_delay=True))
            self.auto_update_started = True
            print("🔄 Auto-update loop started.")