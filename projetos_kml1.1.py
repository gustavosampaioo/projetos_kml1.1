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
import time
import random

def validar_kml(caminho_arquivo):
    try:
        with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
            etree.parse(arquivo)
        return True
    except etree.XMLSyntaxError as e:
        st.error(f"Erro de sintaxe no arquivo KML: {e}")
        return False

def calcular_distancia_linestring(coordinates):
    distancia_total = 0.0
    for i in range(len(coordinates) - 1):
        ponto_atual = coordinates[i]
        proximo_ponto = coordinates[i + 1]
        distancia_total += geodesic(ponto_atual, proximo_ponto).meters
    return round(distancia_total, 0)

def extrair_estilos(root):
    estilos = {}
    for estilo in root.findall(".//{http://www.opengis.net/kml/2.2}Style"):
        style_id = estilo.get("id")
        linestyle = estilo.find(".//{http://www.opengis.net/kml/2.2}LineStyle")
        if linestyle is not None:
            color_tag = linestyle.find(".//{http://www.opengis.net/kml/2.2}color")
            if color_tag is not None:
                kml_color = color_tag.text.strip()
                color = f"#{kml_color[6:8]}{kml_color[4:6]}{kml_color[2:4]}"
                estilos[style_id] = color
    return estilos

def processar_folder_link(folder, estilos):
    parent = folder.getparent()
    while parent is not None:
        if hasattr(parent, 'name') and "GPON" in parent.name.text.upper():
            return 0.0, [], [], [], [], False
        parent = parent.getparent()
    
    distancia_folder = 0.0
    dados = []
    coordenadas_folder = []
    dados_em_andamento = []
    dados_concluido = []
    
    nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
    is_link_parceiros = "LINK PARCEIROS" in nome_folder.upper()
    
    if is_link_parceiros:
        color = "red"
    elif "AMARELO" in nome_folder.upper():
        color = "yellow"
    elif "VERDE" in nome_folder.upper():
        color = "green"
    else:
        color = "blue"
    
    if is_link_parceiros:
        for placemark in folder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
            nome_placemark = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
            
            for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                coordinates = line_string.coordinates.text.strip().split()
                coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                
                distancia = calcular_distancia_linestring(coordinates)
                distancia_folder += distancia
                
                dados.append([nome_folder, nome_placemark, distancia])
                coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))
        
        return distancia_folder, dados, coordenadas_folder, [], [], is_link_parceiros
    
    for subfolder in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        subfolder_name = subfolder.name.text if hasattr(subfolder, 'name') else "Subpasta Desconhecida"
        
        is_em_andamento = "EM ANDAMENTO" in subfolder_name.upper()
        is_concluido = "CONCLUÍDO" in subfolder_name.upper()
        
        for placemark in subfolder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
            nome_placemark = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
            
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
                
                if is_em_andamento:
                    dados_em_andamento.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "dashed"))
                elif is_concluido:
                    dados_concluido.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))
                else:
                    dados.append([nome_folder, nome_placemark, distancia])
                    coordenadas_folder.append((nome_placemark, coordinates, color, "solid"))
    
    return distancia_folder, dados, coordenadas_folder, dados_em_andamento, dados_concluido, is_link_parceiros

def buscar_ctos(folder, ctos_processados=None):
    if ctos_processados is None:
        ctos_processados = set()
    
    ctos = []
    
    for subpasta in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
        
        if "CTO'S" in nome_subpasta.upper() and nome_subpasta not in ctos_processados:
            ctos_processados.add(nome_subpasta)
            dados_cto = {"nome": nome_subpasta, "rotas": []}
            
            rotas = subpasta.findall(".//{http://www.opengis.net/kml/2.2}Folder")
            for rota in rotas:
                nome_rota = rota.name.text if hasattr(rota, 'name') else "Rota Desconhecida"
                placemarks = rota.findall(".//{http://www.opengis.net/kml/2.2}Placemark")
                dados_cto["rotas"].append({
                    "nome_rota": nome_rota,
                    "quantidade_placemarks": len(placemarks)
                })
            
            ctos.append(dados_cto)
        
        ctos.extend(buscar_ctos(subpasta, ctos_processados))
    
    return ctos

def processar_gpon(root):
    dados_gpon = {}
    
    for folder in root.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
        nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
        
        if "GPON" in nome_folder.upper():
            dados_gpon[nome_folder] = {"primeiro_nivel": []}
            
            for subpasta in folder.findall("{http://www.opengis.net/kml/2.2}Folder"):
                nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
                
                dados_subpasta = {"nome": nome_subpasta, "ctos": buscar_ctos(subpasta), "linestrings": []}
                
                for placemark in subpasta.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                    for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                        coordinates = line_string.coordinates.text.strip().split()
                        coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                        distancia = calcular_distancia_linestring(coordinates)
                        dados_subpasta["linestrings"].append((placemark.name.text if hasattr(placemark, 'name') else "Sem Nome", distancia))
                
                dados_gpon[nome_folder]["primeiro_nivel"].append(dados_subpasta)
    
    return dados_gpon

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

        if nome_folder in dados_por_pasta:
            continue

        if "LINK" in nome_folder.upper():
            distancia_folder, dados, coordenadas_folder, em_andamento, concluido, is_link_parceiros = processar_folder_link(folder, estilos)
            distancia_total += distancia_folder

            if is_link_parceiros:
                dados_link_parceiros.extend(dados)
                coordenadas_por_pasta.setdefault(nome_folder, []).extend(coordenadas_folder)
            else:
                if nome_folder not in dados_por_pasta:
                    dados_por_pasta[nome_folder] = (distancia_folder, [])
                dados_por_pasta[nome_folder][1].extend(dados)
                coordenadas_por_pasta.setdefault(nome_folder, []).extend(coordenadas_folder)
                dados_em_andamento.extend(em_andamento)
                dados_concluido.extend(concluido)

        if "CIDADES" in nome_folder.upper():
            for placemark in folder.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                nome = placemark.name.text if hasattr(placemark, 'name') else "Sem Nome"
                point = placemark.find(".//{http://www.opengis.net/kml/2.2}Point")
                if point is not None:
                    coords = point.coordinates.text.strip().split(',')
                    lon = float(coords[0])
                    lat = float(coords[1])
                    cidades_coords.append((nome, (lat, lon)))

        if "GPON" in nome_folder.upper():
            if nome_folder not in dados_gpon:
                dados_gpon[nome_folder] = {"primeiro_nivel": []}

            for subpasta in folder.findall("{http://www.opengis.net/kml/2.2}Folder"):
                nome_subpasta = subpasta.name.text if hasattr(subpasta, 'name') else "Subpasta Desconhecida"
                
                if any(sp["nome"] == nome_subpasta for sp in dados_gpon[nome_folder]["primeiro_nivel"]):
                    continue

                dados_subpasta = {"nome": nome_subpasta, "ctos": buscar_ctos(subpasta), "linestrings": []}

                for placemark in subpasta.findall(".//{http://www.opengis.net/kml/2.2}Placemark"):
                    for line_string in placemark.findall(".//{http://www.opengis.net/kml/2.2}LineString"):
                        coordinates = line_string.coordinates.text.strip().split()
                        coordinates = [tuple(map(float, coord.split(',')[:2][::-1])) for coord in coordinates]
                        distancia = calcular_distancia_linestring(coordinates)
                        dados_subpasta["linestrings"].append((placemark.name.text if hasattr(placemark, 'name') else "Sem Nome", distancia))

                dados_gpon[nome_folder]["primeiro_nivel"].append(dados_subpasta)

    return distancia_total, dados_por_pasta, coordenadas_por_pasta, cidades_coords, dados_gpon, dados_em_andamento, dados_concluido, dados_link_parceiros

def criar_dashboard_gpon(dados_gpon):
    dados_tabela = []
    
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                total_rotas = 0
                total_placemarks = 0
                soma_distancia = 0.0
                
                if "ctos" in subpasta:
                    for cto in subpasta["ctos"]:
                        if "rotas" in cto:
                            total_rotas += len(cto["rotas"])
                            for rota in cto["rotas"]:
                                total_placemarks += rota["quantidade_placemarks"]
                
                if "linestrings" in subpasta:
                    soma_distancia = sum(distancia for _, distancia in subpasta["linestrings"])
                
                dados_tabela.append([
                    subpasta["nome"],
                    total_rotas,
                    total_placemarks,
                    soma_distancia
                ])
    
    df_tabela = pd.DataFrame(
        dados_tabela,
        columns=["POP", "Rotas", "CTO'S", "Fibra Ótica (metros)"]
    )
    
    df_tabela.insert(0, "ID", range(1, len(df_tabela) + 1))
    
    df_tabela.loc["Total"] = [
        "",
        "Total",
        df_tabela["Rotas"].sum(),
        df_tabela["CTO'S"].sum(),
        df_tabela["Fibra Ótica (metros)"].sum()
    ]
    
    df_tabela.set_index("ID", inplace=True)
    
    st.write("### GPON - Análise Rotas, CTO'S, Fibra Ótica")
    st.dataframe(df_tabela)

def criar_tabela_interativa_gpon(dados_gpon):
    if not dados_gpon:
        st.warning("Nenhum dado GPON disponível para análise.")
        return
    
    if not any("primeiro_nivel" in dados for dados in dados_gpon.values()):
        st.error("Estrutura de dados GPON inválida.")
        return
    
    unique_id = f"{int(time.time() * 1000)}_{random.randint(0, 1000000)}"
    
    opcoes_primeiro_nivel = ["TODAS"]
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                if subpasta["nome"] not in opcoes_primeiro_nivel:
                    opcoes_primeiro_nivel.append(subpasta["nome"])
    
    selecionado = st.selectbox(
        "Selecione o POP para análise:",
        opcoes_primeiro_nivel,
        key=f"select_pop_{unique_id}"
    )
    
    if selecionado == "TODAS":
        st.write("### Informações de TODOS os POPs")
        
        dados_tabela_rotas = []
        dados_tabela_quantidade_rotas = []
        
        for nome_gpon, dados in dados_gpon.items():
            if "primeiro_nivel" in dados:
                for subpasta in dados["primeiro_nivel"]:
                    if "ctos" in subpasta:
                        for cto in subpasta["ctos"]:
                            quantidade_rotas = 0
                            if "rotas" in cto:
                                for rota in cto["rotas"]:
                                    dados_tabela_rotas.append([
                                        cto["nome"],
                                        rota["nome_rota"],
                                        rota["quantidade_placemarks"]
                                    ])
                                    quantidade_rotas += 1
                            
                            dados_tabela_quantidade_rotas.append([
                                cto["nome"],
                                quantidade_rotas
                            ])
        
        df_tabela_quantidade_rotas = pd.DataFrame(
            dados_tabela_quantidade_rotas,
            columns=["Projeto", "Rotas"]
        )
        
        df_tabela_quantidade_rotas.insert(0, "ID", range(1, len(df_tabela_quantidade_rotas) + 1))
        total_rotas = df_tabela_quantidade_rotas["Rotas"].sum()
        df_tabela_quantidade_rotas.loc["Total"] = ["", "Total", total_rotas]
        df_tabela_quantidade_rotas.set_index("ID", inplace=True)
        
        st.write("#### Quantidade de Rotas por projeto")
        st.dataframe(df_tabela_quantidade_rotas, key=f"qtd_rotas_{unique_id}")
        
        df_tabela_rotas = pd.DataFrame(
            dados_tabela_rotas,
            columns=["Projeto", "Rota", "CTO'S"]
        )
        
        df_tabela_rotas.insert(0, "ID", range(1, len(df_tabela_rotas) + 1))
        total_placemarks = df_tabela_rotas["CTO'S"].sum()
        df_tabela_rotas.loc["Total"] = ["", "Total", "", total_placemarks]
        df_tabela_rotas.set_index("ID", inplace=True)
        
        st.write("#### Rotas e CTO's")
        st.dataframe(df_tabela_rotas, key=f"rotas_ctos_{unique_id}")
    else:
        for nome_gpon, dados in dados_gpon.items():
            if "primeiro_nivel" in dados:
                for subpasta in dados["primeiro_nivel"]:
                    if subpasta["nome"] == selecionado:
                        st.write(f"### Informações de: {selecionado}")
                        
                        dados_tabela_rotas = []
                        dados_tabela_quantidade_rotas = []
                        
                        if "ctos" in subpasta:
                            for cto in subpasta["ctos"]:
                                quantidade_rotas = 0
                                if "rotas" in cto:
                                    for rota in cto["rotas"]:
                                        dados_tabela_rotas.append([
                                            cto["nome"],
                                            rota["nome_rota"],
                                            rota["quantidade_placemarks"]
                                        ])
                                        quantidade_rotas += 1
                                
                                dados_tabela_quantidade_rotas.append([
                                    cto["nome"],
                                    quantidade_rotas
                                ])
                        
                        df_tabela_quantidade_rotas = pd.DataFrame(
                            dados_tabela_quantidade_rotas,
                            columns=["Projeto", "Rotas"]
                        )
                        
                        df_tabela_quantidade_rotas.insert(0, "ID", range(1, len(df_tabela_quantidade_rotas) + 1))
                        total_rotas = df_tabela_quantidade_rotas["Rotas"].sum()
                        df_tabela_quantidade_rotas.loc["Total"] = ["", "Total", total_rotas]
                        df_tabela_quantidade_rotas.set_index("ID", inplace=True)
                        
                        st.write("#### Quantidade de Rotas por projeto")
                        st.dataframe(df_tabela_quantidade_rotas, key=f"qtd_rotas_{selecionado}_{unique_id}")
                        
                        df_tabela_rotas = pd.DataFrame(
                            dados_tabela_rotas,
                            columns=["Projeto", "Rota", "CTO'S"]
                        )
                        
                        df_tabela_rotas.insert(0, "ID", range(1, len(df_tabela_rotas) + 1))
                        total_placemarks = df_tabela_rotas["CTO'S"].sum()
                        df_tabela_rotas.loc["Total"] = ["", "Total", "", total_placemarks]
                        df_tabela_rotas.set_index("ID", inplace=True)
                        
                        st.write("#### Rotas e CTO's")
                        st.dataframe(df_tabela_rotas, key=f"rotas_ctos_{selecionado}_{unique_id}")

def calcular_porcentagem_concluida(dados_por_pasta, dados_concluido):
    porcentagens = {}
    
    for nome_folder, (distancia_total, _) in dados_por_pasta.items():
        distancia_concluida = sum(linha[2] for linha in dados_concluido if linha[0] == nome_folder)
        
        if distancia_total > 0:
            porcentagem = (distancia_concluida / distancia_total) * 100
        else:
            porcentagem = 0.0
        
        porcentagens[nome_folder] = porcentagem
    
    return porcentagens

def criar_grafico_pizza_porcentagem_concluida(porcentagens, dados_por_pasta, root):
    def esta_dentro_gpon(pasta, root):
        for folder in root.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
            nome_folder = folder.name.text if hasattr(folder, 'name') else "Desconhecido"
            if "GPON" in nome_folder.upper():
                for subfolder in folder.findall(".//{http://www.opengis.net/kml/2.2}Folder"):
                    subfolder_name = subfolder.name.text if hasattr(subfolder, 'name') else "Subpasta Desconhecida"
                    if subfolder_name == pasta:
                        return True
        return False

    pastas_filtradas = [pasta for pasta in porcentagens.keys() if not esta_dentro_gpon(pasta, root)]
    opcoes_pastas = ["Todas os Projetos"] + pastas_filtradas
    pasta_selecionada = st.selectbox("Selecione a pasta para visualizar o gráfico:", opcoes_pastas, key=f"select_pasta_{time.time()}")

    if pasta_selecionada == "Todas os Projetos":
        for pasta in pastas_filtradas:
            porcentagem = porcentagens[pasta]
            porcentagem_nao_concluida = 100 - porcentagem

            df_pizza = pd.DataFrame({
                "Status": ["Concluído", "Não Concluído"],
                "Porcentagem": [porcentagem, porcentagem_nao_concluida]
            })

            fig = px.pie(
                df_pizza,
                values="Porcentagem",
                names="Status",
                title=f"Porcentagem Concluída - {pasta}",
                color="Status",
                color_discrete_map={"Concluído": "green", "Não Concluído": "red"}
            )

            st.plotly_chart(fig)
    else:
        porcentagem = porcentagens[pasta_selecionada]
        porcentagem_nao_concluida = 100 - porcentagem

        df_pizza = pd.DataFrame({
            "Status": ["Concluído", "Não Concluído"],
            "Porcentagem": [porcentagem, porcentagem_nao_concluida]
        })

        fig = px.pie(
            df_pizza,
            values="Porcentagem",
            names="Status",
            title=f"Porcentagem Concluída - {pasta_selecionada}",
            color="Status",
            color_discrete_map={"Concluído": "green", "Não Concluído": "red"}
        )

        st.plotly_chart(fig)

def criar_orcamento_materiais(dados_gpon):
    # Inicializa listas para armazenar dados
    dados_orcamento = []
    
    # Itera sobre todas as GPONs e suas subpastas
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for subpasta in dados["primeiro_nivel"]:
                # Calcula a soma das distâncias das LineStrings (já em metros)
                soma_distancia = sum(distancia for _, distancia in subpasta["linestrings"])
                
                if soma_distancia > 0:  # Só inclui POPs com fibra
                    # Aplica 20% de acréscimo para o total de CABO 2FO
                    total_cabo = soma_distancia * 1.20
                    
                    # Calcula a quantidade de cada material
                    fecho = total_cabo / 50
                    supa = total_cabo / 50
                    alca_branca = total_cabo / 25
                    arame_espinar = total_cabo / 3500
                    fita_aco = total_cabo / 1000
                    plaqueta_identificacao = total_cabo / 120  
                    
                    # Adiciona os dados à lista
                    dados_orcamento.append([
                        subpasta["nome"],  # Nome do POP
                        round(total_cabo, 2),  # CABO 2FO Total (m)
                        round(fecho, 2),      # Fecho
                        round(supa, 2),       # Supa
                        round(alca_branca, 2),# Alça Branca
                        round(arame_espinar, 2), # Arame Espinar
                        round(fita_aco, 2),   # Fita de Aço
                        round(plaqueta_identificacao, 2)  # Plaqueta de Identificação
                    ])
    
    # Cria o DataFrame completo
    df_orcamento = pd.DataFrame(
        dados_orcamento,
        columns=[
            "POP",
            "CABO 2FO Total (m)",
            "Fecho (un)",
            "Supa (un)", 
            "Alça Branca (un)",
            "Arame Espinar (un)", 
            "Fita de Aço (un)",   
            "Plaqueta (un)"
        ]
    )
    
    # Adiciona a coluna ID
    df_orcamento.insert(0, "ID", range(1, len(df_orcamento) + 1))
    
    # Adiciona uma linha de total
    df_orcamento.loc["Total"] = [
        "",
        "Total",
        df_orcamento["CABO 2FO Total (m)"].sum(),
        df_orcamento["Fecho (un)"].sum(),
        df_orcamento["Supa (un)"].sum(),
        df_orcamento["Alça Branca (un)"].sum(),
        df_orcamento["Arame Espinar (un)"].sum(),
        df_orcamento["Fita de Aço (un)"].sum(),
        df_orcamento["Plaqueta (un)"].sum()
    ]
    
    # Define a coluna ID como índice
    df_orcamento.set_index("ID", inplace=True)
    
    return df_orcamento

def criar_tabela_quantitativo_ctos_splitters(dados_gpon):
    # Dicionário de mapeamento de sequência para tipo de Splitter
    SEQUENCIA_SPLITTER = {
        1: "5/95",
        2: "5/95",
        3: "5/95",
        4: "5/95",
        5: "10/90",
        6: "10/90",
        7: "10/90",
        8: "10/90",
        9: "15/85",
        10: "20/80",
        11: "30/70",
        12: "40/60",
        13: "50/50"
    }
    
    dados_tabela = []
    
    for nome_gpon, dados in dados_gpon.items():
        if "primeiro_nivel" in dados:
            for pop in dados["primeiro_nivel"]:
                if "ctos" in pop and pop["ctos"]:
                    total_ctos = 0
                    contador_sequencia = 1  # Inicia a contagem da sequência
                    splitters = {
                        "5/95": 0,
                        "10/90": 0,
                        "15/85": 0,
                        "20/80": 0,
                        "30/70": 0,
                        "40/60": 0,
                        "50/50": 0
                    }
                    
                    # Processa cada CTO no POP
                    for cto in pop["ctos"]:
                        if "rotas" in cto:
                            # Processa cada rota na CTO
                            for rota in cto["rotas"]:
                                qtd_ctos = rota["quantidade_placemarks"]
                                total_ctos += qtd_ctos
                                
                                # Determina o tipo de splitter baseado na sequência atual
                                if contador_sequencia in SEQUENCIA_SPLITTER:
                                    splitter_type = SEQUENCIA_SPLITTER[contador_sequencia]
                                    splitters[splitter_type] += 1
                                
                                # Incrementa o contador de sequência
                                contador_sequencia += 1
                    
                    # Adiciona os dados à lista
                    dados_tabela.append([
                        pop["nome"],
                        total_ctos,
                        splitters["5/95"],
                        splitters["10/90"],
                        splitters["15/85"],
                        splitters["20/80"],
                        splitters["30/70"],
                        splitters["40/60"],
                        splitters["50/50"]
                    ])
    
    # Cria o DataFrame completo
    df_quantitativo = pd.DataFrame(
        dados_tabela,
        columns=[
            "POP",
            "Total CTO's",
            "Splitter 5/95 (Rotas)",
            "Splitter 10/90 (Rotas)", 
            "Splitter 15/85 (Rotas)",
            "Splitter 20/80 (Rotas)", 
            "Splitter 30/70 (Rotas)",   
            "Splitter 40/60 (Rotas)",
            "Splitter 50/50 (Rotas)"
        ]
    )
    
    # Adiciona a coluna ID
    df_quantitativo.insert(0, "ID", range(1, len(df_quantitativo) + 1))
    
    # Adiciona uma linha de total
    df_quantitativo.loc["Total"] = [
        "",
        "Total",
        df_quantitativo["Total CTO's"].sum(),
        df_quantitativo["Splitter 5/95 (Rotas)"].sum(),
        df_quantitativo["Splitter 10/90 (Rotas)"].sum(),
        df_quantitativo["Splitter 15/85 (Rotas)"].sum(),
        df_quantitativo["Splitter 20/80 (Rotas)"].sum(),
        df_quantitativo["Splitter 30/70 (Rotas)"].sum(),
        df_quantitativo["Splitter 40/60 (Rotas)"].sum(),
        df_quantitativo["Splitter 50/50 (Rotas)"].sum()
    ]
    
    # Define a coluna ID como índice
    df_quantitativo.set_index("ID", inplace=True)
    
    return df_quantitativo

# Configuração do aplicativo Streamlit
st.title("Analisador de Projetos de Fibra Ótica")
st.write("""
Este aplicativo analisa um arquivo no formato .kml e exibe informações dinâmicas e interativas 
sobre projetos de fibra ótica, incluindo distâncias, status das rotas, e muito mais.
""")

uploaded_file = st.file_uploader("Carregue um arquivo KML", type=["kml"])

if uploaded_file is not None:
    with open("temp.kml", "wb") as f:
        f.write(uploaded_file.getbuffer())

    if validar_kml("temp.kml"):
        st.write("Processando o arquivo KML...")
        distancia_total, dados_por_pasta, coordenadas_por_pasta, cidades_coords, dados_gpon, dados_em_andamento, dados_concluido, dados_link_parceiros = processar_kml("temp.kml")
    else:
        st.stop()
      
    st.subheader("Mapa do Link entre Cidades")
    
    mapa = folium.Map(location=[-5.0892, -42.8016], zoom_start=5, tiles="Esri WorldImagery")
    
    for nome_folder, coordenadas_folder in coordenadas_por_pasta.items():
        for nome_placemark, coordinates, color, line_style in coordenadas_folder:
            distancia = calcular_distancia_linestring(coordinates)
            
            if line_style == "dashed":
                dash_array = "7, 7"
                weight = 4
                opacity = 1.0
            else:
                dash_array = None
                weight = 4
                opacity = 1.0
            
            folium.PolyLine(
                coordinates,
                color=color,
                weight=weight,
                opacity=opacity,
                dash_array=dash_array,
                tooltip=f"{nome_folder} - {nome_placemark} | Distância: {distancia} metros"
            ).add_to(mapa)
    
    for nome_cidade, coords in cidades_coords:
        casa_icon = CustomIcon(
            icon_image="https://fontetelecom.com.br/infraestrutura/assets/img/logo/logo-1.png",
            icon_size=(40, 20)
        )
            
        folium.Marker(
            location=coords,
            tooltip=nome_cidade,
            icon=casa_icon
        ).add_to(mapa)
    
    folium_static(mapa)
    
    if dados_link_parceiros:
        st.subheader("ROTAS LINK PARCEIROS")
        
        df_link_parceiros = pd.DataFrame(
            dados_link_parceiros,
            columns=["Pasta", "Rota", "Distância (m)"]
        )
        
        df_link_parceiros.insert(0, "ID", range(1, len(df_link_parceiros) + 1))
        subtotal_por_pasta = df_link_parceiros.groupby("Pasta")["Distância (m)"].sum().reset_index()
        subtotal_por_pasta.columns = ["Pasta", "Subtotal"]
        
        dados_tabela_link_parceiros = []
        
        for _, rota in df_link_parceiros.iterrows():
            dados_tabela_link_parceiros.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
        
        for _, subtotal in subtotal_por_pasta.iterrows():
            dados_tabela_link_parceiros.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
        
        total_geral = df_link_parceiros["Distância (m)"].sum()
        dados_tabela_link_parceiros.append(["", "Total", "", total_geral])
        
        df_tabela_final = pd.DataFrame(
            dados_tabela_link_parceiros,
            columns=["ID", "Pasta", "Rota", "Distância (m)"]
        )
        
        df_tabela_final.set_index("ID", inplace=True)
        st.dataframe(df_tabela_final)
    
    st.subheader("Quantidade de Fibra Ótica projetada - LINK")
    
    dados_tabela_pastas = []
    
    for nome_folder, (distancia_folder, dados) in dados_por_pasta.items():
        for linha in dados:
            dados_tabela_pastas.append([nome_folder, linha[1], linha[2]])
    
    for linha in dados_em_andamento:
        dados_tabela_pastas.append([linha[0], linha[1], linha[2]])
    
    for linha in dados_concluido:
        dados_tabela_pastas.append([linha[0], linha[1], linha[2]])
    
    df_tabela_pastas = pd.DataFrame(
        dados_tabela_pastas,
        columns=["Pasta", "ROTAS LINK", "Distância (m)"]
    )
    
    subtotais_pastas = df_tabela_pastas.groupby("Pasta")["Distância (m)"].sum().reset_index()
    subtotais_pastas.columns = ["Pasta", "Subtotal"]
    
    df_tabela_pastas.insert(0, "ID", range(1, len(df_tabela_pastas) + 1))
    
    dados_tabela_final = []
    
    for _, linha in df_tabela_pastas.iterrows():
        dados_tabela_final.append([linha["ID"], linha["Pasta"], linha["ROTAS LINK"], linha["Distância (m)"]])
    
    for _, subtotal in subtotais_pastas.iterrows():
        dados_tabela_final.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
    
    total_geral = df_tabela_pastas["Distância (m)"].sum()
    dados_tabela_final.append(["", "Total", "", total_geral])
    
    df_tabela_final = pd.DataFrame(
        dados_tabela_final,
        columns=["ID", "Pasta", "ROTAS LINK", "Distância (m)"]
    )
    
    df_tabela_final.set_index("ID", inplace=True)
    st.dataframe(df_tabela_final)
    
    if dados_em_andamento or dados_concluido:
        st.subheader("Status das Rotas - LINK")
        
        if dados_em_andamento:
            st.write("#### Rotas em Andamento")
            df_em_andamento = pd.DataFrame(
                dados_em_andamento,
                columns=["Pasta", "Rota", "Distância (m)"]
            )
            df_em_andamento.insert(0, "ID", range(1, len(df_em_andamento) + 1))
            
            subtotal_em_andamento = df_em_andamento.groupby("Pasta")["Distância (m)"].sum().reset_index()
            subtotal_em_andamento.columns = ["Pasta", "Subtotal"]
            
            dados_tabela_em_andamento = []
            
            for _, rota in df_em_andamento.iterrows():
                dados_tabela_em_andamento.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
            
            for _, subtotal in subtotal_em_andamento.iterrows():
                dados_tabela_em_andamento.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
            
            total_em_andamento = df_em_andamento["Distância (m)"].sum()
            dados_tabela_em_andamento.append(["", "Total", "", total_em_andamento])
            
            df_tabela_final_em_andamento = pd.DataFrame(
                dados_tabela_em_andamento,
                columns=["ID", "Pasta", "Rota", "Distância (m)"]
            )
            
            df_tabela_final_em_andamento.set_index("ID", inplace=True)
            st.dataframe(df_tabela_final_em_andamento)
        
        if dados_concluido:
            st.write("#### Rotas Concluídas")
            df_concluido = pd.DataFrame(
                dados_concluido,
                columns=["Pasta", "Rota", "Distância (m)"]
            )
            df_concluido.insert(0, "ID", range(1, len(df_concluido) + 1))
            
            subtotal_concluido = df_concluido.groupby("Pasta")["Distância (m)"].sum().reset_index()
            subtotal_concluido.columns = ["Pasta", "Subtotal"]
            
            dados_tabela_concluido = []
            
            for _, rota in df_concluido.iterrows():
                dados_tabela_concluido.append([rota["ID"], rota["Pasta"], rota["Rota"], rota["Distância (m)"]])
            
            for _, subtotal in subtotal_concluido.iterrows():
                dados_tabela_concluido.append(["", subtotal["Pasta"], "Subtotal", subtotal["Subtotal"]])
            
            total_concluido = df_concluido["Distância (m)"].sum()
            dados_tabela_concluido.append(["", "Total", "", total_concluido])
            
            df_tabela_final_concluido = pd.DataFrame(
                dados_tabela_concluido,
                columns=["ID", "Pasta", "Rota", "Distância (m)"]
            )
            
            df_tabela_final_concluido.set_index("ID", inplace=True)
            st.dataframe(df_tabela_final_concluido)

    with open("temp.kml", 'r', encoding='utf-8') as arquivo:
        root = parser.parse(arquivo).getroot()
    
    porcentagens_concluidas = calcular_porcentagem_concluida(dados_por_pasta, dados_concluido)
    criar_grafico_pizza_porcentagem_concluida(porcentagens_concluidas, dados_por_pasta, root)
    
    criar_dashboard_gpon(dados_gpon)
    
    criar_tabela_interativa_gpon(dados_gpon)
    
    # Na seção de exibição do orçamento:
    st.subheader("📊 Lista Completa de Materiais por POP")
    
    if dados_gpon:
        df_orcamento = criar_orcamento_materiais(dados_gpon)
        st.dataframe(df_orcamento)
        
        st.markdown("""
        **📝 Fórmulas de Cálculo:**
        - **CABO 2FO Total:** Distância projetada + 20% margem
        - **Fecho:** CABO 2FO Total ÷ 50 metros
        - **Supa:** CABO 2FO Total ÷ 50 metros  
        - **Alça Branca:** CABO 2FO Total ÷ 25 metros
        - **Arame Espinar:** CABO 2FO Total ÷ 3.500 metros
        - **Fita de Aço:** CABO 2FO Total ÷ 1.000 metros
        - **Plaqueta:** CABO 2FO Total ÷ 120 metros
        """)

    # Na seção principal do dashboard:
    if dados_gpon:
        st.subheader("📊 Quantitativo de CTO's e Splitters por POP")
        
        df_splitters = criar_tabela_quantitativo_ctos_splitters(dados_gpon)
        st.dataframe(df_splitters)
        
        st.markdown("""
        **📝 Regras de Distribuição:**
        - **Total CTO's:** Soma de todos placemarks em todas as rotas
        - **Splitters:** Contagem de rotas por tipo, seguindo a sequência:
          - Rotas 1-4: Splitter 5/95
          - Rotas 5-8: Splitter 10/90  
          - Rota 9: Splitter 15/85
          - Rota 10: Splitter 20/80
          - Rota 11: Splitter 30/70
          - Rota 12: Splitter 40/60
          - Rota 13: Splitter 50/50
        - **Observação:** A sequência é contada globalmente para todas as rotas do POP
        """)
