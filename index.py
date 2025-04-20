import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
import yt_dlp as youtube_dl
import psutil

# Load env vars
load_dotenv()
DISCORD_TOKEN = os.getenv("discord_token")

# Set process priority
def set_high_priority():
    try:
        p = psutil.Process(os.getpid())
        if os.name == 'nt':  
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:  
            p.nice(-5)
    except Exception as e:
        print(f"Couldn't set process priority: {e}")

set_high_priority()

# Set up bot 
intents = discord.Intents().all()
bot = commands.Bot(command_prefix='-', intents=intents)

# YouTube DL 
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'force-ipv4': True,
    'geo-bypass': True,
    'socket_timeout': 5,
    'retries': 10,
    'buffer_size': 1024*1024*8,
    'http_chunk_size': 1048576,
}

# FFmpeg 
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = f"https://youtu.be/{data.get('id')}"  
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        
        # Check if input is a URL or search query
        is_url = url.startswith(('http://', 'https://'))
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(
                url if is_url else f"ytsearch:{url}",
                download=False
            ))
            
            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print(f"Error extracting info: {e}")
            raise

# Bot events
@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    print('------')

# commands
@bot.command(name='join', help='Joins your voice channel')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("You're not connected to a voice channel!")
        return

    channel = ctx.author.voice.channel
    await channel.connect()

@bot.command(name='leave', help='Leaves the voice channel')
async def leave(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("I'm not connected to a voice channel!")

@bot.command(name='play', help='Plays audio from YouTube (URL or search query)')
async def play(ctx, *, query):
    try:
        if not ctx.author.voice:
            return await ctx.send("You're not connected to a voice channel!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            except Exception as e:
                return await ctx.send(f"❌ Couldn't find or play that song: {str(e)}")
            
            if voice_client.is_playing():
                voice_client.stop()
                
            voice_client.play(
                player, 
                after=lambda e: print(f'Playback error: {e}') if e else None
            )
            
        # Create embed for display
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"[{player.title}]({player.url})",
            color=discord.Color.blue()
        )
        if player.thumbnail:
            embed.set_thumbnail(url=player.thumbnail)
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        print(f"Playback error: {e}")
        
@bot.command(name='pause', help='Pauses the current track')
async def pause(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Playback paused")
    else:
        await ctx.send("❌ I'm not playing anything right now!")

@bot.command(name='resume', help='Resumes the current track')
async def resume(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Playback resumed")
    else:
        await ctx.send("❌ I'm not paused!")

@bot.command(name='stop', help='Stops the current track')
async def stop(ctx):
    voice_client = ctx.voice_client
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await ctx.send("⏹️ Playback stopped")
    else:
        await ctx.send("❌ I'm not playing anything right now!")

@bot.command(name='volume', help='Adjusts the volume (0-200)')
async def volume(ctx, volume: int):
    voice_client = ctx.voice_client
    if not voice_client:
        return await ctx.send("❌ Not connected to a voice channel.")

    if 0 < volume <= 200:
        voice_client.source.volume = volume / 100
        await ctx.send(f"🔊 Volume set to {volume}%")
    else:
        await ctx.send("❌ Please enter a value between 1 and 200")

# Error handling
@play.error
async def play_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Please provide a song name or URL after the command")

# Run the smart bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
