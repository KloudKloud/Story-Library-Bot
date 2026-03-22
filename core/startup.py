class StartupManager:

    def __init__(self):
        self.add_worker_started = False

    async def start_add_worker(self, bot, add_worker):

        if not self.add_worker_started:
            bot.loop.create_task(add_worker())
            self.add_worker_started = True
            print("📚 Add worker started.")