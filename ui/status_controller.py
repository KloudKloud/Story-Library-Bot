class StatusController:

    def __init__(self, interaction):
        self.interaction = interaction
        self.message = None
        self.steps = []

    async def start(self, text):
        self.steps = [text]
        self.message = await self.interaction.followup.send(text)

    async def step(self, text):
        self.steps.append(text)
        await self._refresh()

    async def replace_last(self, text):
        if self.steps:
            self.steps[-1] = text
        else:
            self.steps.append(text)
        await self._refresh()

    async def finish(self, text):
        await self.message.edit(content=text)

    async def error(self, err):
        await self.message.edit(content=f"❌ Error:\n`{err}`")

    async def _refresh(self):
        await self.message.edit(content="\n".join(self.steps))