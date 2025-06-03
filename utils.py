"""
Module d'utilitaires pour l'analyse des fichiers OptiFine CIT

Ce module contient des fonctions utilitaires utilisées par les différents modules d'analyse.
"""

import os
from pathlib import Path
from configparser import ConfigParser
import json
from typing import Dict, List, Optional, Union

def find_file_in_pack(root_path, relative_path: str, extension=None):
    """
    Recherche un fichier dans différents chemins relatifs à partir d'une racine.
    
    Args:
        root_path (str): Chemin du dossier ou fichier racine (si fichier, on prendra le dossier parent)
        relative_path (str): Chemin relatif à chercher
        extension (str, optional): Extension à ajouter si le chemin relatif ne la contient pas
        
    Returns:
        str: Chemin complet relatif à analyse-target si trouvé, None sinon
    """
    
    namespaces = [
        "minecraft",
        "herobrine",
        "miniaturia",
        "modelengine",
        "space",
        "cocricot"
    ]
    
    # Suppression du préfixe minecraft: si présent
    if ":" in relative_path:
        namespaces = [relative_path[:relative_path.index(":")]]
        relative_path = relative_path[relative_path.index(":") + 1:]
    
    # Si root_path est un fichier, on prend son dossier parent
    if os.path.isfile(root_path):
        root_path = os.path.dirname(root_path)
    
    # Normalise les chemins pour utiliser des slashes
    root_path = root_path.replace(os.sep, "/")
    relative_path = relative_path.replace(os.sep, "/")
    
    # Ajoute l'extension si nécessaire
    if extension and not relative_path.endswith(extension):
        relative_path = f"{relative_path}{extension}"
    
    # Liste des chemins de base à essayer
    base_paths = [
        root_path,  # Commence par le root_path
        "PACK_HB",
        "PACK_HB/assets",
        "PACK_HB/assets/{namespace}",
        "PACK_HB/assets/{namespace}/optifine",
        "PACK_HB/assets/{namespace}/optifine/cit",
        "PACK_HB/assets/{namespace}/textures",
        "PACK_HB/assets/{namespace}/models"
    ]
    
    for namespace in namespaces:
        for base_path in base_paths:
            # Construit le chemin complet
            full_path = os.path.join(base_path.format(namespace=namespace), relative_path)
            full_path = full_path.replace(os.sep, "/")

            # Vérifie si le fichier existe
            if os.path.exists(full_path):
                return full_path
    
    # Si aucun chemin n'a fonctionné, retourne None
    return None

def create_markdown_link(source_file: str, target_file: str):
    """
    Crée un lien Markdown vers un fichier, en calculant le chemin relatif correct.
    
    Args:
        source_file (str): Chemin du fichier source (.md) relatif au workspace
        target_file (str): Chemin du fichier cible relatif au workspace
        
    Returns:
        str: Lien Markdown au format [filename](filepath)
    """
    # Normalise les chemins pour utiliser des slashes
    source_file = source_file.replace(os.sep, "/")
    target_file = target_file.replace(os.sep, "/")
    
    # Extrait le nom du fichier cible
    target_filename = os.path.basename(target_file)
    
    # Calcule le chemin relatif du fichier cible par rapport au fichier source
    source_dir = os.path.dirname(source_file)
    relative_path = os.path.relpath(target_file, source_dir).replace(os.sep, "/")
    
    # Crée le lien Markdown
    return f"[{target_filename}]({relative_path})"

def read_properties_file(file_path: str | Path) -> dict[str, str]:
    """
    Lit un fichier .properties et retourne son contenu sous forme de dictionnaire.
    
    Args:
        file_path (str | Path): Chemin vers le fichier .properties
        
    Returns:
        dict[str, str]: Dictionnaire contenant les propriétés du fichier
    """
    properties = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Ignore les lignes vides et les commentaires
                if not line or line.startswith('#'):
                    continue
                
                # Extrait la clé et la valeur (tout avant et après le premier '=')
                if '=' in line:
                    key, value = line.split('=', 1)
                    properties[key.strip()] = value.strip()
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier {file_path}: {e}")
    
    return properties

def get_all_cit_properties() -> List[Path]:
    """
    Récupère tous les chemins des fichiers .properties dans le dossier cit.
    
    Returns:
        List[Path]: Liste des chemins des fichiers .properties
    """
    cit_dir = Path('PACK_HB/assets/minecraft/optifine/cit')
    if not cit_dir.exists():
        return []
    
    properties_files = []
    for root, _, files in os.walk(cit_dir):
        for file in files:
            if file.endswith('.properties'):
                properties_files.append(Path(root) / file)
    
    return properties_files 