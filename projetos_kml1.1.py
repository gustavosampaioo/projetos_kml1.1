import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from pykml import parser
from geopy.distance import geodesic
import plotly.express as px
from folium.features import CustomIcon
from folium import Icon
from lxml import etree

def validar_kml(caminho_arquivo):
    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
            etree.parse(arquivo)
        return True
    except etree.XMLSyntaxError as e:
        st.error(f"Erro de sintaxe no arquivo KML: {e}")
        return False



# Função para calcular a distância total de uma LineString em metros
def calcular_distancia_linestring(coordinates):
    distancia_total = 0.0
    for i in range(len(coordinates) - 1):
        ponto_atual = coordinates[i]
        proximo_ponto = coordinates[i + 1]
        distancia_total += geodesic(ponto_atual, proximo_ponto).meters
    return round(distancia_total, 0)  # Arredonda para 0 casas decimais

# Função para extrair estilos do KML (LineStyle)
def extrair_estilos(root):
    estilos = {}
    for estilo in root.findall(".//{http://www.opengis.net/kml/2.2}Style"):
        style_id = estilo.get("id")
        # Extrai cor do LineStyle
        linestyle = estilo.find(".//{http://www.opengis.net/kml/2.2}LineStyle")
        if linestyle is not None:
            color_tag = linestyle.find(".//{http://www.opengis.net/kml/2.2}color")
            if color_tag is not None:
                kml_color = color_tag.text.strip()
                color = f"#{kml_color[6:8]}{kml_color[4:6]}{kml_color[2:4]}"
                estilos[style_id] = color
    return estilos


def processar_folder_link(folder, estilos):
    # Verifica se a pasta está dentro de uma pasta "GPON"
    parent = folder.getparent()
    while parent is not None:
        if hasattr(parent, 'name') and "GPON" in parent.name.text.upper():
            return 0.0, [], [], [], [], False  # Retorna valores vazios se estiver dentro de uma pasta GPON
        parent = parent.getparent()
    
    distancia_folder = 0.0
    dados = []
    coordenadas_folder = []
    dados_em_andamento = []
    dados_concluido = []
    
    # Verifica se o nome da pasta contém "LINK PARCEIROS"
    nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
    is_link_parceiros = "LINK PARCEIROS" in nome_folder.upper()
    
    # Define a cor com base no nome da pasta
    if is_link_parceiros:
        color = "red"  # Cor vermelha para "LINK PARCEIROS"
    elif "AMARELO" in nome_folder.upper():
        color = "yellow"
    elif "VERDE" in nome_folder.upper():
        color = "green"
    else:
        color = "blue"  # Cor padrão para "LINK"
    
    # Se for "LINK PARCEIROS", processa diretamente as LineString
    if is_link_parceiros:
        for placemark in folder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
            nome_placemark = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
            
            for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                coordinates = line_string.coordinates.text.strip().split()
                coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                
                distancia = calcular_distancia_linestring(coordinates)
                distancia_folder += distancia
                
                # Adiciona as informações às listas correspondentes
                dados.append([nome_folder, nome_placemark, distancia])  # Inclui o nome da pasta
                coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))  # Sólido para "LINK PARCEIROS"
        
        return distancia_folder, dados, coordenadas_folder, [], [], is_link_parceiros
    
    # Caso contrário, processa como pasta "LINK" normal
    for subfolder in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        subfolder_name = subfolder.name.text if hasattr(subfolder, 'name') else "Subpasta Desconhecida"
        
        # Verifica se a subpasta é "EM ANDAMENTO" ou "CONCLUÍDO"
        is_em_andamento = "EM ANDAMENTO" in subfolder_name.upper()
        is_concluido = "CONCLUÍDO" in subfolder_name.upper()
        
        # Processa as LineString dentro da subpasta
        for placemark in subfolder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
            nome_placemark = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
            
            # Usa a cor definida no estilo
            style_url = placemark.find(".//{http://www.opengis.net/kml/2.2}styleUrl")
            if style_url is not None:
                style_id = style_url.text.strip().lstrip("#")
                if style_id in estilos:
                    color = estilos[style_id]
            
            for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                coordinates = line_string.coordinates.text.strip().split()
                coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                
                distancia = calcular_distancia_linestring(coordinates)
                distancia_folder += distancia
                
                # Adiciona as informações às listas correspondentes
                if is_em_andamento:
                    dados_em_andamento.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "dashed"))  # Tracejado para "EM ANDAMENTO"
                elif is_concluido:
                    dados_concluido.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))  # Sólido para "CONCLUÍDO"
                else:
                    dados.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))  # Sólido para outras pastas
    
    return distancia_folder, dados, coordenadas_folder, dados_em_andamento, dados_concluido, is_link_parceiros



# Função para buscar recursivamente por pastas "CTO'S"
def buscar_ctos(folder, ctos_processados=None):
    if ctos_processados is None:
        ctos_processados = set()  # Conjunto para rastrear pastas "CTO'S" já processadas
    
    ctos = []
    
    for subpasta in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
        
        # Se a subpasta contiver "CTO'S" no nome e ainda não foi processada
        if "CTO'S" in nome_subpasta.upper() and nome_subpasta not in ctos_processados:
            ctos_processados.add(nome_subpasta)  # Marca a pasta como processada
            dados_cto = {"nome": nome_subpasta, "rotas": []}
            
            # Processa as rotas dentro da subpasta CTO'S
            rotas = subpasta.findall(".//{http://www.opengis.net/kml/2.2}Folder")
            for rota in rotas:
                nome_rota = rota.name.text if hasattr(rota, 'name') else "Rota Desconhecida"
                placemarks = rota.findall(".//{http://www.opengis.net/kml/2.2}Placemark")
                dados_cto["rotas"].append({
                    "nome_rota": nome_rota,
                    "quantidade_placemarks": len(placemarks)
                })
            
            ctos.append(dados_cto)
        
        # Busca recursivamente por mais pastas "CTO'S" dentro da subpasta atual
        ctos.extend(buscar_ctos(subpasta, ctos_processados))
    
    return ctos

# Função para processar pastas GPON e suas subpastas
def processar_gpon(root):
    dados_gpon = {}
    
    for folder in root.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
        
        # Verifica se o nome da pasta contém "GPON"
        if "GPON" in nome_folder.upper():
            dados_gpon[nome_folder] = {"primeiro_nivel": []}
            
            # Coleta todas as subpastas do primeiro nível após a pasta GPON
            for subpasta in folder.findall("{http://www.opengis.net/kml/2.2}Folder"):
                nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
                
                # Dados da subpasta do primeiro nível
                dados_subpasta = {"nome": nome_subpasta, "ctos": buscar_ctos(subpasta), "linestrings": []}
                
                # Processa as LineStrings dentro da subpasta
                for placemark in subpasta.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                    for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                        coordinates = line_string.coordinates.text.strip().split()
                        coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                        distancia = calcular_distancia_linestring(coordinates)
                        dados_subpasta["linestrings"].append((placemark.name.text if hasattr(placemark, 'name') else "Sem Nome", distancia))
                
                # Adiciona a subpasta do primeiro nível aos dados da pasta GPON
                dados_gpon[nome_folder]["primeiro_nivel"].append(dados_subpasta)
    
    return dados_gpon

# Função para processar o KML e calcular distâncias
def processar_kml(caminho_arquivo):
    with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
        root = parser.parse(arquivo).getroot()
    
    estilos = extrair_estilos(root)
    distancia_total = 0.0
    dados_por_pasta = {}
    coordenadas_por_pasta = {}
    cidades_coords = []
    dados_em_andamento = []
    dados_concluido = []
    dados_link_parceiros = []
    dados_gpon = {}

    for folder in root.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"

        # Evitar duplicação: Verificar se a pasta já foi processada
        if nome_folder in dados_por_pasta:
            continue  # Se já processamos essa pasta, pulamos para a próxima

        # Processa pastas LINK e LINK PARCEIROS
        if "LINK" in nome_folder.upper():
            distancia_folder, dados, coordenadas_folder, em_andamento, concluido, is_link_parceiros = processar_folder_link(folder, estilos)
            distancia_total += distancia_folder

            # Separa os dados dos "LINK PARCEIROS" dos dados da pasta "LINK"
            if is_link_parceiros:
                dados_link_parceiros.extend(dados)  # Adiciona sem sobrescrever
                coordenadas_por_pasta.setdefault(nome_folder, []).extend(coordenadas_folder)
            else:
                # Adiciona apenas os dados gerais (não "EM ANDAMENTO" ou "CONCLUÍDO") ao dicionário
                if nome_folder not in dados_por_pasta:
                    dados_por_pasta[nome_folder] = (distancia_folder, [])
                dados_por_pasta[nome_folder][1].extend(dados)  # Adiciona sem sobrescrever
                
                coordenadas_por_pasta.setdefault(nome_folder, []).extend(coordenadas_folder)
                dados_em_andamento.extend(em_andamento)
                dados_concluido.extend(concluido)

        # Processa pastas que contenham "CIDADES" no nome
        if "CIDADES" in nome_folder.upper():
            for placemark in folder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                nome = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
                point = placemark.find(".//{http://www.opengis.net/kml/2.2}Point")
                if point is not None:
                    coords = point.coordinates.text.strip().split(',')
                    lon = float(coords[0])
                    lat = float(coords[1])
                    cidades_coords.append((nome, (lat, lon)))

        # Processa pastas GPON
        if "GPON" in nome_folder.upper():
            if nome_folder not in dados_gpon:
                dados_gpon[nome_folder] = {"primeiro_nivel": []}

            for subpasta in folder.findall("{http://www.opengis.net/kml/2.2}Folder"):
                nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
                
                # Evita a duplicação da subpasta
                if any(sp["nome"] == nome_subpasta for sp in dados_gpon[nome_folder]["primeiro_nivel"]):
                    continue  # Já adicionamos essa subpasta, então pulamos

                # Processa dados da subpasta
                dados_subpasta = {"nome": nome_subpasta, "ctos": buscar_ctos(subpasta), "linestrings": []}

                for placemark in subpasta.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                    for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                        coordinates = line_string.coordinates.text.strip().split()
                        coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                        distancia = calcular_distancia_linestring(coordinates)
                        dados_subpasta["linestrings"].append((placemark.name.text if hasattr(placemark, 'name') else "Sem Nome", distancia))

                # Adiciona a subpasta do primeiro nível aos dados da pasta GPON
                dados_gpon[nome_folder]["primeiro_nivel"].append(dados_subpasta)

    return distancia_total, dados_por_pasta, coordenadas_por_pasta, cidades_coords, dados_gpon, dados_em_andamento, dados_concluido, dados_link_parceiros


# Função para criar o dashboard GPON
def criar_dashboard_gpon(dados_gpon):
    
    # Inicializa listas para armazenar dados da tabela
    dados_tabela = []
    
    # Itera sobre todas as GPONs e suas subpastas
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                # Inicializa os totais para a subpasta atual
                total_rotas = 0
                total_placemarks = 0
                soma_distancia = 0.0
                
                # Coleta dados de Rotas e Placemarks
                if "ctos" in subpasta:
                    for cto in subpasta["ctos"]:
                        if "rotas" in cto:
                            total_rotas += len(cto["rotas"])
                            for rota in cto["rotas"]:
                                total_placemarks += rota["quantidade_placemarks"]
                
                # Calcula a soma das distâncias das LineStrings
                if "linestrings" in subpasta:
                    soma_distancia = sum(distancia for _, distancia in subpasta["linestrings"])
                
                # Adiciona os dados da subpasta à lista
                dados_tabela.append([
                    subpasta["nome"],  # Nome da subpasta
                    total_rotas,       # Quantidade de rotas
                    total_placemarks,  # Quantidade de placemarks
                    soma_distancia     # Soma das distâncias das LineStrings
                ])
    
    # Cria o DataFrame para a tabela
    df_tabela = pd.DataFrame(
        dados_tabela,
        columns=["POP", "Rotas", "CTO'S", "Fibra Ótica (metros)"]
    )
    
    # Adiciona a coluna ID
    df_tabela.insert(0, "ID", range(1, len(df_tabela) + 1))
    
    # Adiciona uma linha de total
    df_tabela.loc["Total"] = [
        "",  # ID (vazio para a linha de total)
        "Total",  # Subpasta
        df_tabela["Rotas"].sum(),
        df_tabela["CTO'S"].sum(),
        df_tabela["Fibra Ótica (metros)"].sum()
    ]
    
    # Define a coluna ID como índice do DataFrame
    df_tabela.set_index("ID", inplace=True)
    
    # Exibe a tabela
    st.write("### GPON - Análise Rotas, CTO'S, Fibra Ótica")
    st.dataframe(df_tabela)

# Função para criar uma tabela interativa com seleção de primeiro nível
def criar_tabela_interativa_gpon(dados_gpon):
    # Cria uma lista de opções para o selectbox (primeiro nível)
    opcoes_primeiro_nivel = ["TODAS"]  # Adiciona a opção "TODAS" no início da lista
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                opcoes_primeiro_nivel.append(subpasta["nome"])
    
    # Adiciona um selectbox para selecionar o primeiro nível
    selecionado = st.selectbox("Selecione o POP para análise:", opcoes_primeiro_nivel)
    
    # Verifica se a opção selecionada é "TODAS"
    if selecionado == "TODAS":
        st.write("### Informações de TODOS os POPs")
        
        # Inicializa listas para armazenar dados das tabelas
        dados_tabela_rotas = []  # Tabela de Rotas e CTO's
        dados_tabela_quantidade_rotas = []  # Tabela de Quantidade de Rotas por CTO
        
        # Itera sobre todas as GPONs e suas subpastas
        for nome_gpon, dados in dados_gpon.items():
            if "primeiro_nivel" in dados:
                for subpasta in dados["primeiro_nivel"]:
                    # Coleta dados de Rotas e CTO's
                    if "ctos" in subpasta:
                        for cto in subpasta["ctos"]:
                            quantidade_rotas = 0
                            if "rotas" in cto:
                                for rota in cto["rotas"]:
                                    dados_tabela_rotas.append([
                                        cto["nome"],  # Nome do CTO
                                        rota["nome_rota"],  # Nome da Rota
                                        rota["quantidade_placemarks"]  # Quantidade de Placemarks
                                    ])
                                    quantidade_rotas += 1
                            
                            # Adiciona a quantidade de rotas por CTO
                            dados_tabela_quantidade_rotas.append([
                                cto["nome"],  # Nome do CTO
                                quantidade_rotas  # Quantidade de Rotas
                            ])
        
        # Cria o DataFrame para a tabela de Quantidade de Rotas por CTO
        df_tabela_quantidade_rotas = pd.DataFrame(
            dados_tabela_quantidade_rotas,
            columns=["Projeto", "Rotas"]
        )
        
        # Adiciona a coluna ID
        df_tabela_quantidade_rotas.insert(0, "ID", range(1, len(df_tabela_quantidade_rotas) + 1))
        
        # Adiciona uma linha de total
        total_rotas = df_tabela_quantidade_rotas["Rotas"].sum()
        df_tabela_quantidade_rotas.loc["Total"] = ["", "Total", total_rotas]
        
        # Define a coluna ID como índice do DataFrame
        df_tabela_quantidade_rotas.set_index("ID", inplace=True)
        
        # Exibe a tabela de Quantidade de Rotas por CTO
        st.write("#### Quantidade de Rotas por projeto")
        st.dataframe(df_tabela_quantidade_rotas)
        
        # Cria o DataFrame para a tabela de Rotas e CTO's
        df_tabela_rotas = pd.DataFrame(
            dados_tabela_rotas,
            columns=["Projeto", "Rota", "CTO'S"]
        )
        
        # Adiciona a coluna ID
        df_tabela_rotas.insert(0, "ID", range(1, len(df_tabela_rotas) + 1))
        
        # Adiciona uma linha de total
        total_placemarks = df_tabela_rotas["CTO'S"].sum()
        df_tabela_rotas.loc["Total"] = ["", "Total", "", total_placemarks]
        
        # Define a coluna ID como índice do DataFrame
        df_tabela_rotas.set_index("ID", inplace=True)
        
        # Exibe a tabela de Rotas e CTO's
        st.write("#### Rotas e CTO's")
        st.dataframe(df_tabela_rotas)
    
    else:
        # Encontra os dados correspondentes ao primeiro nível selecionado
        for nome_gpon, dados in dados_gpon.items():
            if "primeiro_nivel" in dados:
                for subpasta in dados["primeiro_nivel"]:
                    if subpasta["nome"] == selecionado:
                        st.write(f"### Informações de: {selecionado}")
                        
                        # Inicializa listas para armazenar dados das tabelas
                        dados_tabela_rotas = []  # Tabela de Rotas e CTO's
                        dados_tabela_quantidade_rotas = []  # Tabela de Quantidade de Rotas por CTO
                        
                        # Coleta dados de Rotas e CTO's
                        if "ctos" in subpasta:
                            for cto in subpasta["ctos"]:
                                quantidade_rotas = 0
                                if "rotas" in cto:
                                    for rota in cto["rotas"]:
                                        dados_tabela_rotas.append([
                                            cto["nome"],  # Nome do CTO
                                            rota["nome_rota"],  # Nome da Rota
                                            rota["quantidade_placemarks"]  # Quantidade de Placemarks
                                        ])
                                        quantidade_rotas += 1
                                
                                # Adiciona a quantidade de rotas por CTO
                                dados_tabela_quantidade_rotas.append([
                                    cto["nome"],  # Nome do CTO
                                    quantidade_rotas  # Quantidade de Rotas
                                ])
                        
                        # Cria o DataFrame para a tabela de Quantidade de Rotas por CTO
                        df_tabela_quantidade_rotas = pd.DataFrame(
                            dados_tabela_quantidade_rotas,
                            columns=["Projeto", "Rotas"]
                        )
                        
                        # Adiciona a coluna ID
                        df_tabela_quantidade_rotas.insert(0, "ID", range(1, len(df_tabela_quantidade_rotas) + 1))
                        
                        # Adiciona uma linha de total
                        total_rotas = df_tabela_quantidade_rotas["Rotas"].sum()
                        df_tabela_quantidade_rotas.loc["Total"] = ["", "Total", total_rotas]
                        
                        # Define a coluna ID como índice do DataFrame
                        df_tabela_quantidade_rotas.set_index("ID", inplace=True)
                        
                        # Exibe a tabela de Quantidade de Rotas por CTO
                        st.write("#### Quantidade de Rotas por projeto")
                        st.dataframe(df_tabela_quantidade_rotas)
                        
                        # Cria o DataFrame para a tabela de Rotas e CTO's
                        df_tabela_rotas = pd.DataFrame(
                            dados_tabela_rotas,
                            columns=["Projeto", "Rota", "CTO'S"]
                        )
                        
                        # Adiciona a coluna ID
                        df_tabela_rotas.insert(0, "ID", range(1, len(df_tabela_rotas) + 1))
                        
                        # Adiciona uma linha de total
                        total_placemarks = df_tabela_rotas["CTO'S"].sum()
                        df_tabela_rotas.loc["Total"] = ["", "Total", "", total_placemarks]
                        
                        # Define a coluna ID como índice do DataFrame
                        df_tabela_rotas.set_index("ID", inplace=True)
                        
                        # Exibe a tabela de Rotas e CTO's
                        st.write("#### Rotas e CTO's")
                        st.dataframe(df_tabela_rotas)

#verificar codigo
def calcular_porcentagem_concluida(dados_por_pasta, dados_concluido):
    porcentagens = {}
    
    # Verificação dos dados
    print("Dados por pasta:", dados_por_pasta)
    print("Dados concluídos:", dados_concluido)
   
    # Itera sobre as pastas e calcula a porcentagem concluída
    for nome_folder, (distancia_total, _) in dados_por_pasta.items():
        # Filtra os dados concluídos para a pasta atual
        distancia_concluida = sum(linha[2] for linha in dados_concluido if linha[0] == nome_folder)
        
        # Verifica se a distância total é maior que zero para evitar divisão por zero
        if distancia_total > 0:
            porcentagem = (distancia_concluida / distancia_total) * 100
        else:
            porcentagem = 0.0
        
        # Armazena a porcentagem no dicionário
        porcentagens[nome_folder] = porcentagem
    
    return porcentagens

# Função para criar o gráfico de pizza de porcentagem concluída com seleção de pasta
def criar_grafico_pizza_porcentagem_concluida(porcentagens, dados_por_pasta, root):
    # Função auxiliar para verificar se uma pasta está dentro de "GPON"
    def esta_dentro_gpon(pasta, root):
        # Percorre a hierarquia do KML para verificar se a pasta está dentro de "GPON"
        for folder in root.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
            nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
            if "GPON" in nome_folder.upper():
                # Verifica se a pasta "LINK" está dentro desta pasta "GPON"
                for subfolder in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
                    subfolder_name = subfolder.name.text if hasattr(subfolder, 'name') else "Subpasta Desconhecida"
                    if subfolder_name == pasta:
                        return True
        return False

    # Filtra as pastas que não estão dentro de uma pasta "GPON"
    pastas_filtradas = [pasta for pasta in porcentagens.keys() if not esta_dentro_gpon(pasta, root)]

    # Cria uma lista de opções para o selectbox (apenas pastas filtradas)
    opcoes_pastas = ["Todas os Projetos"] + pastas_filtradas

    # Adiciona um selectbox para o usuário escolher a pasta
    pasta_selecionada = st.selectbox("Selecione a pasta para visualizar o gráfico:", opcoes_pastas)

    # Verifica se o usuário selecionou "Todas os Projetos"
    if pasta_selecionada == "Todas os Projetos":
        # Itera sobre todas as pastas filtradas e exibe um gráfico para cada uma
        for pasta in pastas_filtradas:
            porcentagem = porcentagens[pasta]
            porcentagem_nao_concluida = 100 - porcentagem

            # Cria o DataFrame para o gráfico de pizza
            df_pizza = pd.DataFrame({
                "Status": ["Concluído", "Não Concluído"],
                "Porcentagem": [porcentagem, porcentagem_nao_concluida]
            })

            # Cria o gráfico de pizza
            fig = px.pie(
                df_pizza,
                values="Porcentagem",
                names="Status",
                title=f"Porcentagem Concluída - {pasta}",
                color="Status",
                color_discrete_map={"Concluído": "green", "Não Concluído": "red"}
            )

            # Exibe o gráfico no Streamlit
            st.plotly_chart(fig)
    else:
        # Exibe apenas o gráfico da pasta selecionada
        porcentagem = porcentagens[pasta_selecionada]
        porcentagem_nao_concluida = 100 - porcentagem

        # Cria o DataFrame para o gráfico de pizza
        df_pizza = pd.DataFrame({
            "Status": ["Concluído", "Não Concluído"],
            "Porcentagem": [porcentagem, porcentagem_nao_concluida]
        })

        # Cria o gráfico de pizza
        fig = px.pie(
            df_pizza,
            values="Porcentagem",
            names="Status",
            title=f"Porcentagem Concluída - {pasta_selecionada}",
            color="Status",
            color_discrete_map={"Concluído": "green", "Não Concluído": "red"}
        )

        # Exibe o gráfico no Streamlit
        st.plotly_chart(fig)

def criar_orcamento_materiais(dados_gpon):
    # Dados de custo (valores fictícios - substitua por valores reais)
    CUSTO_CABO_POR_METRO = 10.00  # R$10,00 por metro de cabo autossustentado 2FO AS80
    PERCENTUAL_ACRESCIMO = 0.20  # 20% de acréscimo para outros materiais
    
    # Inicializa listas para armazenar dados do orçamento
    dados_orcamento = []
    
    # Itera sobre todas as GPONs e suas subpastas
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                # Calcula a soma das distâncias das LineStrings
                soma_distancia = sum(distancia for _, distancia in subpasta["linestrings"])
                
                if soma_distancia > 0:  # Só inclui POPs com fibra
                    # Cálculos do orçamento
                    valor_cabo = soma_distancia * CUSTO_CABO_POR_METRO
                    valor_outros_materiais = valor_cabo * PERCENTUAL_ACRESCIMO
                    valor_total = valor_cabo + valor_outros_materiais
                    
                    # Adiciona os dados à lista
                    dados_orcamento.append([
                        subpasta["nome"],  # Nome do POP
                        soma_distancia,    # Metros de cabo
                        valor_cabo,
                        valor_outros_materiais,
                        valor_total
                    ])
    
    # Cria o DataFrame para o orçamento
    df_orcamento = pd.DataFrame(
        dados_orcamento,
        columns=[
            "POP", 
            "Cabo (metros)", 
            "Cabo Autossustentado 2FO AS80 (R$)", 
            "Outros Materiais (20%) (R$)", 
            "Valor Total (R$)"
        ]
    )
    
    # Adiciona a coluna ID
    df_orcamento.insert(0, "ID", range(1, len(df_orcamento) + 1))
    
    # Adiciona uma linha de total
    df_orcamento.loc["Total"] = [
        "",
        "Total",
        df_orcamento["Cabo (metros)"].sum(),
        df_orcamento["Cabo Autossustentado 2FO AS80 (R$)"].sum(),
        df_orcamento["Outros Materiais (20%) (R$)"].sum(),
        df_orcamento["Valor Total (R$)"].sum()
    ]
    
    # Formata os valores monetários
    for col in ["Cabo Autossustentado 2FO AS80 (R$)", "Outros Materiais (20%) (R$)", "Valor Total (R$)"]:
        df_orcamento[col] = df_orcamento[col].apply(lambda x: f"R$ {x:,.2f}" if isinstance(x, (int, float)) else x)
    
    # Define a coluna ID como índice do DataFrame
    df_orcamento.set_index("ID", inplace=True)
    
    return df_orcamento


    
# Configuração do aplicativo Streamlit
st.title("Analisador de Projetos de Fibra Ótica")
st.write("""
Este aplicativo analisa um arquivo no formato .kml e exibe informações dinâmicas e interativas 
sobre projetos de fibra ótica, incluindo distâncias, status das rotas, e muito mais.
""")


# Upload do arquivo KML
uploaded_file = st.file_uploader("Carregue um arquivo KML", type=["kml"])

# Verifica se um arquivo foi carregado
if uploaded_file is not None:

       # Salva o arquivo temporariamente
    with open("temp.kml", "wb") as f:
        f.write(uploaded_file.getbuffer())

    if validar_kml("temp.kml"):
        st.write("Processando o arquivo KML...")
        distancia_total, dados_por_pasta, coordenadas_por_pasta, cidades_coords, dados_gpon, dados_em_andamento, dados_concluido, dados_link_parceiros = processar_kml("temp.kml")
    else:
        st.stop()  # Interrompe a execução se o arquivo for inválido
      
    # Exibe o mapa e outras informações
    st.subheader("Mapa do Link entre Cidades")
    
    # Cria o mapa Folium
    mapa = folium.Map(location=[-5.0892, -42.8016], zoom_start=5, tiles="Esri WorldImagery")
    
    # Adiciona LineStrings e marcadores ao mapa
    for nome_folder, coordenadas_folder in coordenadas_por_pasta.items():
        for nome_placemark, coordinates, color, line_style in coordenadas_folder:
            # Calcula a distância da LineString
            distancia = calcular_distancia_linestring(coordinates)
            
            # Define o estilo da linha
            if line_style == "dashed":
                dash_array = "7, 7"  # Tracejado mais perceptível
                weight = 4  # Espessura maior para destacar
                opacity = 1.0  # Opacidade total (sem linha de fundo)
            else:
                dash_array = None  # Linha sólida
                weight = 4  # Espessura padrão
                opacity = 1.0  # Opacidade padrão
            
            # Adiciona a LineString ao mapa
            folium.PolyLine(
                coordinates,
                color=color,  # Cor da linha
                weight=weight,  # Espessura da linha
                opacity=opacity,  # Opacidade da linha
                dash_array=dash_array,  # Aplica o tracejado apenas para "EM ANDAMENTO"
                tooltip=f"{nome_folder} - {nome_placemark} | Distância: {distancia} metros"
            ).add_to(mapa)
    
    # Adiciona marcadores das cidades ao mapa com ícone personalizado
    for nome_cidade, coords in cidades_coords:
        casa_icon = CustomIcon(
            icon_image="https://fontetelecom.com.br/infraestrutura/assets/img/logo/logo-1.png",  # URL de um ícone de casa
            icon_size=(40, 20)  # Tamanho do ícone (largura, altura)
        )
        
        folium.Marker(
            location=coords,
            tooltip=nome_cidade,
            icon=casa_icon  # Usa o ícone personalizado
        ).add_to(mapa)
    
    # Exibe o mapa no Streamlit
    folium_static(mapa)
    
    # Exibe tabela para "LINK PARCEIROS"
    if dados_link_parceiros:
        st.subheader("ROTAS LINK PARCEIROS")
        
        # Cria o DataFrame para a tabela dos "LINK PARCEIROS"
        df_link_parceiros = pd.DataFrame(
            dados_link_parceiros,
            columns=["Pasta", "Rota", "Distância (m)"]
        )
        
        # Adiciona a coluna ID
        df_link_parceiros.insert(0, "ID", range(1, len(df_link_parceiros) + 1))
        
        # Calcula o subtotal por pasta
        subtotal_por_pasta = df_link_parceiros.groupby("Pasta")["Distância (m)"].sum().reset_index()
        subtotal_por_pasta.columns = ["Pasta", "Subtotal"]
        
        # Cria uma lista para armazenar as linhas da tabela
        dados_tabela_link_parceiros = []
        
        # Adiciona todas as rotas primeiro
        for _, rota in df_link_parceiros.iterrows():
            dados_tabela_link_parceiros.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
        
        # Adiciona os subtotais no final
        for _, subtotal in subtotal_por_pasta.iterrows():
            dados_tabela_link_parceiros.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
        
        # Calcula o total geral
        total_geral = df_link_parceiros["Distância (m)"].sum()
        
        # Adiciona a linha de total geral
        dados_tabela_link_parceiros.append(["", "Total", "", total_geral])
        
        # Cria o DataFrame final
        df_tabela_final = pd.DataFrame(
            dados_tabela_link_parceiros,
            columns=["ID", "Pasta", "Rota", "Distância (m)"]
        )
        
        # Define a coluna ID como índice do DataFrame
        df_tabela_final.set_index("ID", inplace=True)
        
        # Exibe a tabela
        st.dataframe(df_tabela_final)
    
    # Exibe tabelas para pastas LINK
    st.subheader("Quantidade de Fibra Ótica projetada - LINK")
    
    # Lista para armazenar todos os dados
    dados_tabela_pastas = []
    
    # Adiciona os dados gerais (não "EM ANDAMENTO" ou "CONCLUÍDO")
    for nome_folder, (distancia_folder, dados) in dados_por_pasta.items():
        for linha in dados:
            dados_tabela_pastas.append([nome_folder, linha[1], linha[2]])  # [Pasta, Rota, Distância]
    
    # Adiciona os dados de "EM ANDAMENTO"
    for linha in dados_em_andamento:
        dados_tabela_pastas.append([linha[0], linha[1], linha[2]])  # [Pasta, Rota, Distância]
    
    # Adiciona os dados de "CONCLUÍDO"
    for linha in dados_concluido:
        dados_tabela_pastas.append([linha[0], linha[1], linha[2]])  # [Pasta, Rota, Distância]
    
    # Cria o DataFrame principal
    df_tabela_pastas = pd.DataFrame(
        dados_tabela_pastas,
        columns=["Pasta", "ROTAS LINK", "Distância (m)"]
    )
    
    # Agrupa os dados por pasta e calcula os subtotais
    subtotais_pastas = df_tabela_pastas.groupby("Pasta")["Distância (m)"].sum().reset_index()
    subtotais_pastas.columns = ["Pasta", "Subtotal"]
    
    # Adiciona uma coluna de ID ao DataFrame principal
    df_tabela_pastas.insert(0, "ID", range(1, len(df_tabela_pastas) + 1))
    
    # Cria uma lista para armazenar as linhas da tabela final
    dados_tabela_final = []
    
    # Adiciona todas as rotas primeiro
    for _, linha in df_tabela_pastas.iterrows():
        dados_tabela_final.append([linha["ID"], linha["Pasta"], linha["ROTAS LINK"], linha["Distância (m)"]])
    
    # Adiciona os subtotais por pasta
    for _, subtotal in subtotais_pastas.iterrows():
        dados_tabela_final.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
    
    # Calcula o total geral
    total_geral = df_tabela_pastas["Distância (m)"].sum()
    
    # Adiciona a linha de total geral
    dados_tabela_final.append(["", "Total", "", total_geral])
    
    # Cria o DataFrame final
    df_tabela_final = pd.DataFrame(
        dados_tabela_final,
        columns=["ID", "Pasta", "ROTAS LINK", "Distância (m)"]
    )
    
    # Define a coluna ID como índice do DataFrame
    df_tabela_final.set_index("ID", inplace=True)
    
    # Exibe a tabela
    st.dataframe(df_tabela_final)
    
    # Exibe tabelas para "EM ANDAMENTO" e "CONCLUÍDO"
    if dados_em_andamento or dados_concluido:
        st.subheader("Status das Rotas - LINK")
        
        # Tabela para "EM ANDAMENTO"
        if dados_em_andamento:
            st.write("#### Rotas em Andamento")
            df_em_andamento = pd.DataFrame(
                dados_em_andamento,
                columns=["Pasta", "Rota", "Distância (m)"]
            )
            df_em_andamento.insert(0, "ID", range(1, len(df_em_andamento) + 1))
            
            # Calcula o subtotal por pasta
            subtotal_em_andamento = df_em_andamento.groupby("Pasta")["Distância (m)"].sum().reset_index()
            subtotal_em_andamento.columns = ["Pasta", "Subtotal"]
            
            # Cria uma lista para armazenar as linhas da tabela
            dados_tabela_em_andamento = []
            
            # Adiciona todas as rotas primeiro
            for _, rota in df_em_andamento.iterrows():
                dados_tabela_em_andamento.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
            
            # Adiciona os subtotais no final
            for _, subtotal in subtotal_em_andamento.iterrows():
                dados_tabela_em_andamento.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
            
            # Calcula o total geral
            total_em_andamento = df_em_andamento["Distância (m)"].sum()
            
            # Adiciona a linha de total geral
            dados_tabela_em_andamento.append(["", "Total", "", total_em_andamento])
            
            # Cria o DataFrame final
            df_tabela_final_em_andamento = pd.DataFrame(
                dados_tabela_em_andamento,
                columns=["ID", "Pasta", "Rota", "Distância (m)"]
            )
            
            # Define a coluna ID como índice do DataFrame
            df_tabela_final_em_andamento.set_index("ID", inplace=True)
            
            # Exibe a tabela
            st.dataframe(df_tabela_final_em_andamento)
        
        # Tabela para "CONCLUÍDO"
        if dados_concluido:
            st.write("#### Rotas Concluídas")
            df_concluido = pd.DataFrame(
                dados_concluido,
                columns=["Pasta", "Rota", "Distância (m)"]
            )
            df_concluido.insert(0, "ID", range(1, len(df_concluido) + 1))
            
            # Calcula o subtotal por pasta
            subtotal_concluido = df_concluido.groupby("Pasta")["Distância (m)"].sum().reset_index()
            subtotal_concluido.columns = ["Pasta", "Subtotal"]
            
            # Cria uma lista para armazenar as linhas da tabela
            dados_tabela_concluido = []
            
            # Adiciona todas as rotas primeiro
            for _, rota in df_concluido.iterrows():
                dados_tabela_concluido.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
            
            # Adiciona os subtotais no final
            for _, subtotal in subtotal_concluido.iterrows():
                dados_tabela_concluido.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
            
            # Calcula o total geral
            total_concluido = df_concluido["Distância (m)"].sum()
            
            # Adiciona a linha de total geral
            dados_tabela_concluido.append(["", "Total", "", total_concluido])
            
            # Cria o DataFrame final
            df_tabela_final_concluido = pd.DataFrame(
                dados_tabela_concluido,
                columns=["ID", "Pasta", "Rota", "Distância (m)"]
            )
            
            # Define a coluna ID como índice do DataFrame
            df_tabela_final_concluido.set_index("ID", inplace=True)
            
            # Exibe a tabela
            st.dataframe(df_tabela_final_concluido)

    # Obtém o root do KML
    with open("temp.kml", 'r', encoding='utf-8') as arquivo:
        root = parser.parse(arquivo).getroot()
    
    # Calcula a porcentagem concluída por pasta
    porcentagens_concluidas = calcular_porcentagem_concluida(dados_por_pasta, dados_concluido)
    
    # Cria o gráfico de porcentagem concluída
    grafico_porcentagem = criar_grafico_pizza_porcentagem_concluida(porcentagens_concluidas, dados_por_pasta, root)
    
    # Exibe o dashboard GPON
    criar_dashboard_gpon(dados_gpon)
    
    # Exibe a tabela interativa
    criar_tabela_interativa_gpon(dados_gpon)

    # Exibe o dashboard GPON
    criar_dashboard_gpon(dados_gpon)
    
    # Exibe a tabela interativa
    criar_tabela_interativa_gpon(dados_gpon)
    
    # ============= NOVA SEÇÃO PARA ORÇAMENTO =============
    st.subheader("📊 Orçamento de Materiais para o Projeto")
    
    # Cria e exibe o orçamento
    if dados_gpon:
        df_orcamento = criar_orcamento_materiais(dados_gpon)
        st.dataframe(df_orcamento)
        
        # Adiciona informações explicativas
        st.markdown("""
        **📝 Legenda do Orçamento:**
        - **Cabo Autossustentado 2FO AS80:** Valor calculado com base na metragem total de fibra por POP
        - **Outros Materiais (20%):** Inclui conectores, caixas de emenda, fixadores e demais materiais complementares
        - **Valor Total:** Soma do custo do cabo com os outros materiais
        
        *Observação: Valores calculados considerando R$ 10,00 por metro de cabo e 20% para outros materiais.*
        """)
    
    # ============= FIM DA NOVA SEÇÃO =============

