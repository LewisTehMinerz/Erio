import discord
import textwrap
import time
from discord.ext import commands
from utils import permissions
from utils import randomness
import aiohttp
import asyncio
import subprocess
import rethinkdb as r

class Admin:
    def __init__(self, bot):
        self.bot = bot
        self.conn = bot.conn
        self._eval = {}

    async def haste_upload(self, text):
        with aiohttp.ClientSession() as sesh:
            async with sesh.post("https://hastebin.com/documents/", data=text, headers={"Content-Type": "text/plain"}) as r:
                r = await r.json()
                return r['key']
            
    @permissions.owner()
    async def set_avy(self, ctx, *, avy : str):
        'Avatar setter'
        async with aiohttp.ClientSession() as sesh:
            async with sesh.get(avy) as r:
                await self.bot.user.edit(avatar=await r.read())
                await ctx.send(":ok_hand:")

    @commands.command(aliases=["ev", "e"])
    @permissions.owner()
    async def eval(self, ctx, *, code: str):
        """Evaluates Python code"""
        if self._eval.get('env') is None:
            self._eval['env'] = {}
        if self._eval.get('count') is None:
            self._eval['count'] = 0

        codebyspace = code.split(" ")
        print(codebyspace)
        silent = False
        if codebyspace[0] == "--silent" or codebyspace[0] == "-s": 
            silent = True
            codebyspace = codebyspace[1:]
            code = " ".join(codebyspace)


        self._eval['env'].update({
            'self': self.bot,
            'ctx': ctx,
            'message': ctx.message,
            'channel': ctx.message.channel,
            'guild': ctx.message.guild,
            'author': ctx.message.author,
        })

        # let's make this safe to work with
        code = code.replace('```py\n', '').replace('```', '').replace('`', '')

        _code = 'async def func(self):\n  try:\n{}\n  finally:\n    self._eval[\'env\'].update(locals())'\
            .format(textwrap.indent(code, '    '))

        before = time.monotonic()
        # noinspection PyBroadException
        try:
            exec(_code, self._eval['env'])
            func = self._eval['env']['func']
            output = await func(self)

            if output is not None:
                output = repr(output)
        except Exception as e:
            output = '{}: {}'.format(type(e).__name__, e)
        after = time.monotonic()
        self._eval['count'] += 1
        count = self._eval['count']

        code = code.split('\n')
        if len(code) == 1:
            _in = 'In [{}]: {}'.format(count, code[0])
        else:
            _first_line = code[0]
            _rest = code[1:]
            _rest = '\n'.join(_rest)
            _countlen = len(str(count)) + 2
            _rest = textwrap.indent(_rest, '...: ')
            _rest = textwrap.indent(_rest, ' ' * _countlen)
            _in = 'In [{}]: {}\n{}'.format(count, _first_line, _rest)

        message = '```py\n{}'.format(_in)
        if output is not None:
            message += '\nOut[{}]: {}'.format(count, output)
        ms = int(round((after - before) * 1000))
        if ms > 100:  # noticeable delay
            message += '\n# {} ms\n```'.format(ms)
        else:
            message += '\n```'

        try:
            if ctx.author.id == self.bot.user.id:
                await ctx.message.edit(content=message)
            else:
                if not silent:
                    await ctx.send(message)
        except discord.HTTPException:
            if not silent:
                with aiohttp.ClientSession() as sesh:
                    async with sesh.post("https://hastebin.com/documents/", data=output, headers={"Content-Type": "text/plain"}) as r:
                        r = await r.json()
                        embed = discord.Embed(
                            description="[View output - click](https://hastebin.com/raw/{})".format(r["key"]),
                            color=randomness.random_colour()
                        )
                        await ctx.send(embed=embed)

    @commands.command(aliases=['sys', 's', 'run', 'sh'], description="Run system commands.")
    @permissions.owner()
    async def system(self, ctx, *, command : str):
        'Run system commands.'
        message = await ctx.send('<a:typing:393848431413559296> Processing...')
        result = []
        try:
            process = subprocess.Popen(command.split(' '), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = process.communicate()
        except FileNotFoundError:
            stderr = f'Command not found: {command}'
        embed = discord.Embed(
            title="Command output",
            color=randomness.random_colour()
        )
        if len(result) >= 1 and result[0] in [None, b'']: stdout = 'No output.'
        if len(result) >= 2 and result[0] in [None, b'']: stderr = 'No output.'
        if len(result) >= 1 and result[0] not in [None, b'']: stdout = result[0].decode('utf-8')
        if len(result) >= 2 and result[1] not in [None, b'']: stderr = result[1].decode('utf-8')
        string = ""
        if len(result) >= 1:
            if (len(result[0]) >= 1024): 
                stdout = result[0].decode('utf-8')
                string = string + f'[[STDOUT]]\n{stdout}'
                key = await self.haste_upload(string)
                return await ctx.send(f"http://hastebin.com/{key}")
        if len(result) >= 2:
            if (len(result[1]) >= 1024): 
                stdout = result[0].decode('utf-8')
                string = string + f'[[STDERR]]\n{stdout}'
                key = await self.haste_upload(string)
                return await ctx.send(f"http://hastebin.com/{key}")
        embed.add_field(name="stdout", value=f'```{stdout}```' if 'stdout' in locals() else 'No output.', inline=False)
        embed.add_field(name="stderr", value=f'```{stderr}```' if 'stderr' in locals() else 'No output.', inline=False)
        await message.edit(content='', embed=embed)

    @commands.command(aliases=['game', 'status'])
    @permissions.owner()
    async def setgame(self, ctx, *, status : str):
        'Set game'
        await ctx.bot.change_presence(game=discord.Game(name=status, type=0))
        await ctx.send(':ok_hand:')

    @commands.command()
    @permissions.owner()
    async def maintenance(self, ctx, state : str = None):
        'Put the bot into maintenance mode or back'
        bools = False
        if state is not None:
            if state in ['true', 'false', 'on', 'off']:
                bools = state in ['on', 'true']
        
        if bools == True:
            prompt = await ctx.send('```Are you sure you want to do this? This will make the bot stop responding to anyone but you!\n\n[y]: Enter Maintenance mode\n[n]: Exit prompt```')
            msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
            if msg.content == 'y':
                await prompt.delete()
                await self.bot.change_presence(status=discord.Status.dnd, game=discord.Game(name='Bot is currently being maintained. Please check back later.'))
                self.bot.maintenance = True
                await ctx.send(':white_check_mark: Bot now in maintenance mode.')
                return
            else:
                await prompt.delete()
                await ctx.send('Prompt exited.')
        elif bools == False:
            self.bot.maintenance = False
            await self.bot.change_presence(status=discord.Status.online, game=None)
            await ctx.send(':white_check_mark: Bot not in maintenance mode anymore.')




def setup(bot):
    bot.add_cog(Admin(bot))