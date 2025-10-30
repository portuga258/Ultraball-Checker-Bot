# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import requests
import json
import re
from bs4 import BeautifulSoup
import os # Importar a biblioteca os para checar o arquivo local

# --- Configurações ---
# ATENÇÃO: Nunca compartilhe este código com o Token em ambientes públicos.
# TOKEN do seu bot do Discord. Já preenchido com o token fornecido.
TOKEN = os.getenv('DISCORD_TOKEN')

# Nome do arquivo local de dados (deve estar na mesma pasta do bot)
LOCAL_DATA_FILE = "pokemons.json"

# Variável global para armazenar os dados dos Pokémons carregados.
POKEMON_DATA_CACHE = {}

# Variável para rastrear a contagem de comandos por usuário (em memória).
# ATENÇÃO: Esta contagem será perdida se o bot for reiniciado.
USER_REQUEST_COUNTS = {}
PIX_KEY = "f88cbe7a-f244-44d8-b6f8-a3a88af516e0"
PIX_INTERVAL = 10 # Intervalo de requests para pedir PIX

# Mapeamento de Tipos: (Seu Tipo no JSON Limpo/Sem Acento: Tipo Oficial)
# Este mapeamento inclui TODAS as variações comuns em português (com acento removido)
# para garantir que todos os Pokémons recebam a sugestão de Pokebola correta.
TIPO_MAPPER = {
    # Tipos Metálicos / Aço
    'metal': 'STEEL',
    'aco': 'STEEL',        # Adicionado para cobrir 'Aço'
    
    'psiquico': 'PSYCHIC', # Psíquico
    'fantasma': 'GHOST',
    
    # Tipos Sombrio / Noturno
    'sombrio': 'DARK',
    'noturno': 'DARK',
    
    'eletrico': 'ELECTRIC', # Elétrico
    'gelo': 'ICE',
    'voador': 'FLYING',
    
    # Tipos Rocha / Pedra
    'rocha': 'ROCK',
    'pedra': 'ROCK',
    
    'lutador': 'FIGHTING',
    'normal': 'NORMAL',
    'dragao': 'DRAGON',    # Dragão
    'fada': 'FAIRY',
    'inseto': 'BUG',
    
    # Tipos Aquáticos / Água
    'aquatico': 'WATER', 
    'agua': 'WATER',
    
    # Tipos Terrestres / Venenosos
    'venenoso': 'POISON',
    'grama': 'GRASS',
    'fogo': 'FIRE',
    
    # Tipos Terrestre / Chão / Terra
    'terrestre': 'GROUND', 
    'chao': 'GROUND',
    'terra': 'GROUND',     # Adicionado para cobrir 'Terra'
}

# Configuração dos Intents (Permissões do Bot)
intents = discord.Intents.default()
intents.message_content = True

# Criação do Bot
# O prefixo agora é '!', e o comando é 'poke'.
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)


# --- Funções de Carregamento de Dados ---

def load_pokemon_data():
    """
    Tenta carregar os dados do arquivo local (pokemons.json).
    Se o arquivo local for encontrado, ele mapeia as chaves de tabela para as chaves de uso do bot,
    incluindo todas as informações solicitadas.
    """
    global POKEMON_DATA_CACHE
    
    # Função robusta para remover acentos, cedilha e padronizar minúsculas antes do lookup
    def clean_type_key(name):
        # 1. Converte para minúsculas primeiro para padronizar
        name = str(name).lower()
        # 2. Dicionário de substituição para acentos
        replacements = {
            'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a', 
            'é': 'e', 'ê': 'e', 'ë': 'e', 
            'í': 'i', 'î': 'i', 'ï': 'i', 
            'ó': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
            'ú': 'u', 'ü': 'u',
            'ç': 'c',
            # Versões maiúsculas
            'Á': 'a', 'À': 'a', 'Ã': 'a', 'Â': 'a', 'Ä': 'a',
            'É': 'e', 'Ê': 'e', 'Ë': 'e',
            'Í': 'i', 'Î': 'i', 'Ï': 'i',
            'Ó': 'o', 'Õ': 'o', 'Ô': 'o', 'Ö': 'o',
            'Ú': 'u', 'Ü': 'u',
            'Ç': 'c'
        }
        
        for old, new in replacements.items():
            name = name.replace(old, new)
            
        return name.strip() # Garante que não haja espaços em branco indesejados

    if os.path.exists(LOCAL_DATA_FILE):
        print(f"Tentando carregar dados do arquivo local: {LOCAL_DATA_FILE}...")
        try:
            with open(LOCAL_DATA_FILE, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
            
            temp_cache = {}
            for item in data_list:
                if 'nome' in item and 'tableub' in item:
                    name_key = item['nome'].lower().strip() 
                    
                    # Constrói a string de Tipo (Ex: "Fada / Nenhum" ou apenas "Grama")
                    tipo1_json = item.get('tipo1', 'N/A')
                    tipo2_json = item.get('tipo2', 'Nenhum')
                    
                    tipo_completo = f"{tipo1_json}"
                    if tipo2_json and tipo2_json.lower() not in ('nenhum', 'n/a', ''):
                        tipo_completo += f" / {tipo2_json}"
                    
                    # Mapeia os tipos para o formato oficial (necessário para a lógica das Pokebolas)
                    
                    # 1. Limpa o nome do tipo (ex: "Água" -> "agua", "Dragão" -> "dragao")
                    cleaned_tipo1 = clean_type_key(tipo1_json)
                    cleaned_tipo2 = clean_type_key(tipo2_json)
                    
                    # 2. Tenta mapear o tipo limpo. 
                    # Se falhar (o tipo limpo não está no TIPO_MAPPER), usa o tipo original em MAIÚSCULAS
                    # como fallback.
                    tipo1_oficial = TIPO_MAPPER.get(cleaned_tipo1, tipo1_json.upper())
                    tipo2_oficial = TIPO_MAPPER.get(cleaned_tipo2, tipo2_json.upper())
                    
                    # Cria um objeto limpo com TODOS os dados
                    cleaned_item = {
                        'name': item['nome'],
                        
                        # Informações de Tipo e Bolas
                        'tipo': tipo_completo, 
                        'ball1': item.get('ball1', 'N/A'), 
                        'dificuldade': item.get('dificuldade', 'N/A'),
                        'level': str(item.get('level', 'N/A')), 
                        'image': item.get('image', None),
                        
                        # Valores de Bolas de Captura (UB, GB, SB)
                        'tableub': str(item.get('tableub', 'N/A')), 
                        'tablegb': str(item.get('tablegb', 'N/A')), 
                        'tablesb': str(item.get('tablesb', 'N/A')),
                        
                        # Novos Campos para Dicas de Pokebola Específica
                        'fast': item.get('fast', 'no'),
                        'heavy': item.get('heavy', 'no'),
                        'tipo1_oficial': tipo1_oficial, # Tipo primário oficial
                        'tipo2_oficial': tipo2_oficial, # Tipo secundário oficial
                    }
                    temp_cache[name_key] = cleaned_item
            
            POKEMON_DATA_CACHE = temp_cache
            
            if len(POKEMON_DATA_CACHE) > 0:
                print(f"Dados carregados com sucesso do arquivo local. Total de {len(POKEMON_DATA_CACHE)} Pokémons.")
                return True
            else:
                print("ERRO de Dados Locais: O arquivo 'pokemons.json' foi lido, mas não contém Pokémons válidos.")
                return False

        except json.JSONDecodeError:
            print(f"ERRO de JSON: O arquivo '{LOCAL_DATA_FILE}' não é um JSON válido. Verifique a sintaxe.")
            return False
        except Exception as e:
            print(f"ERRO inesperado ao ler o arquivo local: {e}")
            return False
    else:
        print(f"ERRO: Arquivo de dados '{LOCAL_DATA_FILE}' não encontrado na pasta do bot.")
        return False


# --- Eventos do Bot (RESTANTE DO CÓDIGO) ---

@bot.event
async def on_ready():
    """
    Este evento é acionado quando o bot se conecta com sucesso ao Discord.
    """
    print(f"Bot logado como {bot.user.name} ({bot.user.id})")
    print("-" * 43)
    load_pokemon_data()
    await bot.change_presence(activity=discord.Game(name="!poke <nome>"))


@bot.event
async def on_command_error(ctx, error):
    """
    Tratamento de erros para comandos (ex: se o usuário digitar !poke sem um nome).
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ **Erro de Comando:** Por favor, use o formato `!poke <nome do pokemon>` (ex: `!poke pikachu`).")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ **Erro de Sintaxe:** O comando `{ctx.message.content.split()[0]}` não existe. O comando correto é `!poke <nome do pokemon>`.")
    else:
        print(f"Erro inesperado no comando: {error}")
        

# --- Comando Principal ---

@bot.command(name="poke", pass_context=True)
async def check_poke_average(ctx, *, pokemon_name: str):
    """
    Processa o comando !poke <nome do pokemon> e exibe estatísticas em um Embed,
    e verifica a contagem de comandos para o PIX.
    """
    global USER_REQUEST_COUNTS

    if not POKEMON_DATA_CACHE:
        load_pokemon_data() 
        if not POKEMON_DATA_CACHE:
             await ctx.send(f"❌ **Erro de Dados:** O bot não pode funcionar. Verifique o arquivo '{LOCAL_DATA_FILE}'.")
             return

    # 1. Rastreamento e Solicitação de PIX
    user_id = str(ctx.author.id)
    
    # Inicializa ou incrementa a contagem de requests do usuário
    USER_REQUEST_COUNTS[user_id] = USER_REQUEST_COUNTS.get(user_id, 0) + 1
    current_count = USER_REQUEST_COUNTS[user_id]

    # Verifica se a contagem é um múltiplo do intervalo definido (a cada 10 requests)
    if current_count % PIX_INTERVAL == 0:
        pix_message = (
            f"✨ **Aviso de Apoio ao Bot!** ✨\n"
            f"Você já usou o comando `!poke` **{current_count} vezes**! Incrível!\n\n"
            f"Se você gosta do bot e gostaria de ajudar a mantê-lo online e atualizado, "
            f"considere fazer um PIX de qualquer valor para o desenvolvedor.\n"
            # O texto foi atualizado para refletir que a chave é um alias/código e não um e-mail.
            f"🔑 **Chave PIX (Alias/Copia e Cola):** `{PIX_KEY}`\n"
            f"Seu apoio é muito importante! Obrigado!"
        )
        await ctx.send(pix_message)

    # 2. Processamento do Comando !poke (Lógica Existente)
    search_key = pokemon_name.lower().strip()
    result = POKEMON_DATA_CACHE.get(search_key)

    if result:
        # 1. Coleta dos Dados
        name = result.get('name', pokemon_name)
        dificuldade = result.get('dificuldade', 'N/A')
        level = result.get('level', 'N/A')
        image_url = result.get('image', None)
        tipo = result.get('tipo', 'N/A')
        ball1 = result.get('ball1', 'N/A')
        ub_value = result.get('tableub', 'N/A')
        gb_value = result.get('tablegb', 'N/A')
        sb_value = result.get('tablesb', 'N/A')
        
        # Tipos Oficiais para Lógica (Já mapeados na carga de dados)
        tipo1_oficial = result.get('tipo1_oficial', 'N/A')
        tipo2_oficial = result.get('tipo2_oficial', 'N/A')
        
        # Corrigindo a lista de tipos para garantir que não haja erros de case ou N/A
        types_raw = [tipo1_oficial, tipo2_oficial]
        # Esta linha garante que a lista de tipos seja limpa, removendo N/A e padronizando o case
        types = [t.upper() for t in types_raw if t and t.upper() not in ['N/A', 'NENHUM']]


        # 2. Lógica para Sugestão da Melhor Pokebola (AGORA MOSTRA TODAS AS APLICÁVEIS)
        dicas_pokebola = []

        # Fast/Heavy Balls (Baseadas nas flags do JSON)
        if result.get('fast', 'no').lower() == 'yes':
            dicas_pokebola.append("⚡ **Fast Ball** (Maior chance para Pokémons classificados como FAST).")
        
        if result.get('heavy', 'no').lower() == 'yes':
            dicas_pokebola.append("⛰️ **Heavy Ball** (Maior chance para Pokémons classificados como HEAVY).")

        # Pokebolas de Profissão (Engenheiro)
        
        # Moon Ball (GHOST/DARK) - Fantasma/Sombrio/Noturno
        if any(t in types for t in ['GHOST', 'DARK']):
            dicas_pokebola.append("🌕 **Moon Ball** (Superior à UB para tipos GHOST/DARK - Fantasma/Sombrio).")
        
        # Tinker Ball (ELECTRIC/STEEL) - Elétrico/Aço/Metal
        if any(t in types for t in ['ELECTRIC', 'STEEL']):
            dicas_pokebola.append("🔩 **Tinker Ball** (Superior à UB para tipos ELECTRIC/STEEL - Elétrico/Aço).")
            
        # Sora Ball (ICE/FLYING) - Gelo/Voador
        if any(t in types for t in ['ICE', 'FLYING']):
            dicas_pokebola.append("☁️ **Sora Ball** (Superior à UB para tipos ICE/FLYING - Gelo/Voador).")
            
        # Dusk Ball (ROCK/FIGHTING) - Rocha/Pedra/Lutador
        if any(t in types for t in ['ROCK', 'FIGHTING']):
            dicas_pokebola.append("🌑 **Dusk Ball** (Superior à UB para tipos ROCK/FIGHTING - Rocha/Lutador).")
            
        # Yume Ball (NORMAL/PSYCHIC) - Normal/Psíquico
        if any(t in types for t in ['NORMAL', 'PSYCHIC']):
            dicas_pokebola.append("💭 **Yume Ball** (Superior à UB para tipos NORMAL/PSYCHIC - Normal/Psíquico).")
            
        # Tale Ball (DRAGON/FAIRY) - Dragão/Fada
        if any(t in types for t in ['DRAGON', 'FAIRY']):
            dicas_pokebola.append("🐉 **Tale Ball** (Superior à UB para tipos DRAGON/FAIRY - Dragão/Fada).")
            
        # Net Ball (BUG/WATER) - Inseto/Água/Aquático
        if any(t in types for t in ['BUG', 'WATER']):
            dicas_pokebola.append("💧 **Net Ball** (Superior à UB para tipos BUG/WATER - Inseto/Água).")
            
        # Janguru Ball (POISON/GRASS) - Venenoso/Grama
        if any(t in types for t in ['POISON', 'GRASS']):
            dicas_pokebola.append("🌿 **Janguru Ball** (Superior à UB para tipos POISON/GRASS - Venenoso/Grama).")
            
        # Magu Ball (FIRE/GROUND) - Fogo/Terrestre/Chão/Terra
        if any(t in types for t in ['FIRE', 'GROUND']):
            dicas_pokebola.append("🔥 **Magu Ball** (Superior à UB para tipos FIRE/GROUND - Fogo/Terrestre).")

        # Junta todas as dicas encontradas, separando-as por linha.
        dicas_texto = "\n".join(dicas_pokebola) if dicas_pokebola else "Nenhuma Pokebola especial de Engenheiro sugerida."


        # 3. CRIAÇÃO DO EMBED
        embed = discord.Embed(
            title=f"Estatísticas de Captura de {name.upper()}",
            color=discord.Color.blue()
        )
        
        # --- IMAGEM NO TOPO (THUMBNAIL) ---
        # set_thumbnail coloca a imagem no canto superior direito, o que a torna mais visível.
        if image_url:
            embed.set_thumbnail(url=image_url) 
            
        # --- PRIMEIRA LINHA: Tipo e Pokebola Sugerida ---
        embed.add_field(name="Tipo(s)", value=f"`{tipo}`", inline=True)
        embed.add_field(name="Pokebola de Tipo/Status Comum", value=f"`{ball1}`", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Pula linha
        
        # --- SEGUNDA LINHA: Dificuldade e Nível ---
        embed.add_field(name="Dificuldade", value=f"`{dificuldade}`", inline=True)
        embed.add_field(name="Nível de Captura", value=f"`{level}`", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Pula linha
        
        # --- TERCEIRA LINHA: Dicas de Pokebolas Específicas (TODAS AS APLICÁVEIS) ---
        # A lógica agora garante que todos os tipos (Metal/Steel e Psíquico/Psychic) sejam verificados.
        embed.add_field(name="Dicas de Pokebolas de Profissão (Engenheiro)", value=dicas_texto, inline=False)
        embed.add_field(name="\u200b", value="\u200b", inline=False) # Pula linha

        # --- QUARTA LINHA: Valores de Bolas Comuns ---
        embed.add_field(name="Ultra Ball (UB)", value=f"`{ub_value}`", inline=True)
        embed.add_field(name="Great Ball (GB)", value=f"`{gb_value}`", inline=True)
        embed.add_field(name="Super Ball (SB)", value=f"`{sb_value}`", inline=True)

        await ctx.send(embed=embed)
        
    else:
        # Pokémon não encontrado
        await ctx.send(
            f"❓ **Pokémon não encontrado:** Não consegui encontrar dados para **{pokemon_name.upper()}** no arquivo local '{LOCAL_DATA_FILE}'.\n"
            f"**Dica:** Tente usar um Pokémon conhecido, como `!poke Bulbasaur`.\n"
            f"Verifique se o nome está escrito corretamente, incluindo a grafia exata."
        )

# --- Execução ---
# Inicia o bot com o token
bot.run(TOKEN)
