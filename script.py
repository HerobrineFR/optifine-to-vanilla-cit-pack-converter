"""
Module principal pour l'analyse des fichiers CIT (Custom Item Textures) d'OptiFine.

Ce module contient la classe CIT qui permet d'analyser les fichiers .properties
et leurs relations avec les fichiers JSON et les textures.
"""

from pathlib import Path
import json
import json5
import shutil
from utils import create_markdown_link, read_properties_file, find_file_in_pack, get_all_cit_properties
import re

# Chargement de la configuration
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
OUTPUT_PATH = Path(config['output_path'])

def clean_output_directory() -> None:
    """
    Supprime le répertoire de sortie s'il existe et le recrée vide.
    """
    if OUTPUT_PATH.exists():
        shutil.rmtree(OUTPUT_PATH)
    OUTPUT_PATH.mkdir(parents=True)

class ConversionError(Exception):
    """
    Exception parente pour toutes les erreurs de conversion de modèles ou de textures.
    """
    pass

class JsonModelError(ConversionError):
    """
    Exception personnalisée pour les erreurs de validation des modèles JSON.
    
    Attributes:
        json_model (JsonModel): Instance du modèle JSON en erreur
        message (str): Message décrivant l'erreur
    """
    def __init__(self, json_model: 'JsonModel', message: str):
        self.json_model = json_model
        self.message = message
        super().__init__(message)

class JsonModel:
    """
    Classe représentant un modèle JSON.
    
    Attributes:
        json_path (Path): Chemin vers le fichier JSON
        has_not_found_textures (bool): Indique si le modèle a des textures manquantes
        specific_suffix (str): Suffixe spécifique pour différencier les variantes
        output_name (str): Nom de sortie unique pour le modèle converti
    """
    
    # Cache des instances JsonModel
    _instances: dict[Path, 'JsonModel'] = {}
    # Cache des noms de fichiers sans extension
    _file_names: dict[str, Path] = {}
    
    json_path: Path
    has_not_found_textures: bool
    specific_suffix: str
    output_name: str
    
    def __init__(self, json_path: str | Path, specific_suffix: str = ""):
        """
        Initialise une instance de JsonModel avec le chemin vers un fichier JSON.
        
        Args:
            json_path (str | Path): Chemin vers le fichier JSON
            specific_suffix (str): Suffixe spécifique pour différencier les variantes
            
        Raises:
            JsonModelError: Si un autre fichier JSON avec le même nom (sans extension) existe déjà
        """
        self.json_path = Path(json_path)
        self.organization = Organization.get_organization(str(self.json_path))
        self.has_not_found_textures = False
        self.specific_suffix = specific_suffix
        base_name = self.json_path.stem
        self.output_name = f"{base_name}_{specific_suffix}" if specific_suffix else base_name
        
        # Vérification du nom de fichier sans extension
        file_name = self.output_name
        if file_name in JsonModel._file_names and JsonModel._file_names[file_name] != self.json_path:
            raise JsonModelError(self, f"Un autre fichier JSON avec le même nom '{file_name}' existe déjà : {JsonModel._file_names[file_name]}")
        JsonModel._file_names[file_name] = self.json_path
        self.validation()
    
    @classmethod
    def getJsonModel(cls, json_path: str | Path, specific_suffix: str = "") -> 'JsonModel':
        """
        Récupère ou crée une instance de JsonModel pour le chemin donné.
        
        Args:
            json_path (str | Path): Chemin vers le fichier JSON
            specific_suffix (str): Suffixe spécifique pour différencier les variantes
            
        Returns:
            JsonModel: Instance de JsonModel pour le chemin donné
        """
        json_path = Path(json_path)
        key = (json_path, specific_suffix)
        if key not in cls._instances:
            cls._instances[key] = cls(json_path, specific_suffix)
        return cls._instances[key]
    
    def convert(self, texture_override: str | None = None) -> str:
        """
        Convertit le modèle JSON en modifiant son parent et en le sauvegardant dans le dossier de sortie.
        
        Args:
            texture_override (str | None): Si défini, remplace toutes les textures par cette valeur
            
        Returns:
            str: Nouvelle valeur du parent pour le modèle converti
        """
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
            
            # Traitement du parent
            if 'parent' in model_data:
                parent_path = model_data['parent']
                # On essaie toujours de trouver le fichier parent
                parent_file = find_file_in_pack(self.json_path, parent_path, '.json')
                # Si on le trouve, on le convertit et on met à jour le parent
                if parent_file is not None:
                    parent_model = JsonModel.getJsonModel(parent_file, self.specific_suffix)
                    model_data['parent'] = parent_model.convert(texture_override)
                # Sinon, on garde la valeur originale du parent
            
            # Traitement des textures
            if 'textures' in model_data and isinstance(model_data['textures'], dict):
                for texture_key, texture_path in model_data['textures'].items():
                    if texture_override is not None:
                        # Si texture_override est défini, on l'utilise pour toutes les textures
                        model_data['textures'][texture_key] = texture_override
                    else:
                        # Sinon, on essaie de trouver et convertir chaque texture
                        texture_file = find_file_in_pack(self.json_path, texture_path, '.png')
                        if texture_file is not None:
                            png = PNG.getPNG(texture_file)
                            model_data['textures'][texture_key] = png.convert()
                        # Sinon, on garde la valeur originale de la texture
            elif texture_override is not None:
                model_data['textures'] = {
                    "layer0": texture_override
                }
            
            # Ajout de la texture particle
            if 'textures' in model_data and isinstance(model_data['textures'], dict):
                if 'particle' not in model_data['textures']:
                    texture_keys = list(model_data['textures'].keys())
                    if texture_keys:
                        model_data['textures']['particle'] = f"#{texture_keys[0]}"
            
            # Création du dossier de sortie
            output_path = self.organization.get_item_model_path(f"{self.output_name}.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarde du fichier converti
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(model_data, f, indent=2)
            
            return self.organization.get_item_model_ref(f"{self.output_name}.json")
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise JsonModelError(self, f"Erreur lors de la conversion du fichier JSON : {str(e)}")
    
    def validation(self) -> None:
        """
        Valide le contenu du fichier JSON du modèle.
        
        Vérifie que toutes les textures référencées dans le modèle existent.
        Pour chaque texture, on utilise find_file_in_pack avec le chemin du modèle JSON comme root_path.
        Si une texture n'est pas trouvée, on vérifie si son chemin commence par "minecraft:", "item/", "block/" ou "#".
        Si c'est le cas, on ignore l'erreur, sinon on lève une JsonModelError.
        
        Vérifie également le parent du modèle. Si le parent n'est pas trouvé avec find_file_in_pack,
        on vérifie si son chemin commence par "minecraft:", "item/", "block/" ou "builtin/".
        Si c'est le cas, on ignore l'erreur, sinon on lève une JsonModelError.
        
        Raises:
            JsonModelError: Si une texture référencée n'est pas trouvée ou si le parent n'est pas trouvé
        """
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
            
            # Vérification du parent
            if 'parent' in model_data:
                parent_path = model_data['parent']
                parent_file = find_file_in_pack(self.json_path, parent_path, '.json')
                if parent_file is None:
                    if not (parent_path.startswith('minecraft:') or parent_path.startswith('item/') or parent_path.startswith('block/') or parent_path.startswith('builtin/')):
                        raise JsonModelError(self, f"Parent '{parent_path}' non trouvé")
                else:
                    parent_model = JsonModel.getJsonModel(parent_file, self.specific_suffix)
                    parent_model.validation()
            
            # Vérification des textures
            if 'textures' not in model_data:
                self.has_not_found_textures = False
                return
            
            textures = model_data['textures']
            if not isinstance(textures, dict):
                raise JsonModelError(self, "Le champ 'textures' n'est pas un dictionnaire")
            
            for texture_key, texture_path in textures.items():
                if find_file_in_pack(self.json_path, texture_path, '.png') is None:
                    if not (texture_path.startswith('#') or texture_path.startswith('minecraft:') or texture_path.startswith('item/') or texture_path.startswith('block/')):
                        raise JsonModelError(self, f"Texture '{texture_path}' référencée par '{texture_key}' non trouvée")
            
            self.has_not_found_textures = False
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise JsonModelError(self, f"Erreur lors de la lecture du fichier JSON : {str(e)}")

class PNGError(ConversionError):
    """
    Exception personnalisée pour les erreurs de validation des fichiers PNG.
    
    Attributes:
        png (PNG): Instance du fichier PNG en erreur
        message (str): Message décrivant l'erreur
    """
    def __init__(self, png: 'PNG', message: str):
        self.png = png
        self.message = message
        super().__init__(message)

class PNG:
    """
    Classe représentant un fichier PNG.
    
    Attributes:
        png_path (Path): Chemin vers le fichier PNG
    """
    
    # Cache des instances PNG
    _instances: dict[Path, 'PNG'] = {}
    # Cache des noms de fichiers sans extension
    _file_names: dict[str, Path] = {}
    
    png_path: Path
    
    def __init__(self, png_path: str | Path):
        """
        Initialise une instance de PNG avec le chemin vers un fichier PNG.
        
        Args:
            png_path (str | Path): Chemin vers le fichier PNG
            
        Raises:
            PNGError: Si un autre fichier PNG avec le même nom (sans extension) existe déjà
        """
        self.png_path = Path(png_path)
        # Vérification du nom de fichier sans extension
        file_name = self.png_path.stem
        if file_name in PNG._file_names and PNG._file_names[file_name] != self.png_path:
            raise PNGError(self, f"Un autre fichier PNG avec le même nom '{file_name}' existe déjà : {PNG._file_names[file_name]}")
        PNG._file_names[file_name] = self.png_path
        self.organization = Organization.get_organization(self.png_path)
    
    @classmethod
    def getPNG(cls, png_path: str | Path) -> 'PNG':
        """
        Récupère ou crée une instance de PNG pour le chemin donné.
        
        Args:
            png_path (str | Path): Chemin vers le fichier PNG
            
        Returns:
            PNG: Instance de PNG pour le chemin donné
        """
        png_path = Path(png_path)
        if png_path not in cls._instances:
            cls._instances[png_path] = cls(png_path)
        return cls._instances[png_path]
    
    def convert(self, destination: str = "item") -> str:
        if destination == "item":
            output_path = self.organization.get_texture_item_path(f"{self.png_path.name}")
            ref = self.organization.get_texture_item_ref(f"{self.png_path.name}")
        elif destination == "equip_humanoid":
            output_path = self.organization.get_texture_equip_humanoid_path(f"{self.png_path.name}")
            ref = self.organization.get_texture_equip_humanoid_ref(f"{self.png_path.name}")
        elif destination == "equip_humanoid_leggings":
            output_path = self.organization.get_texture_equip_humanoid_leggings_path(f"{self.png_path.name}")
            ref = self.organization.get_texture_equip_humanoid_leggings_ref(f"{self.png_path.name}")
        elif destination == "equip_wings":
            output_path = self.organization.get_texture_equip_wings_path(f"{self.png_path.name}")
            ref = self.organization.get_texture_equip_wings_ref(f"{self.png_path.name}")
        else:
            raise ValueError(f"Destination inconnue: {destination}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.png_path, output_path)
        mcmeta_path = self.png_path.parent / f"{self.png_path.stem}.png.mcmeta"
        if mcmeta_path.exists():
            output_mcmeta_path = output_path.parent / f"{self.png_path.stem}.png.mcmeta"
            shutil.copy2(mcmeta_path, output_mcmeta_path)
        return ref

class GenericJsonModel:
    """
    Classe représentant un modèle JSON générique pour un item.
    
    Attributes:
        item_name (str): Nom de l'item pour lequel générer le modèle
        properties_name (str): Nom du fichier .properties associé
        output_name (str): Nom du fichier de sortie généré
        specific_suffix (str): Suffixe spécifique pour différencier les variantes
    """
    
    # Cache des instances GenericJsonModel
    _instances: dict[tuple[str, str, str], 'GenericJsonModel'] = {}
    item_name: str
    properties_name: str
    output_name: str
    specific_suffix: str
    
    def __init__(self, item_name: str, properties_name: str, specific_suffix: str = "", organization=None):
        """
        Initialise une instance de GenericJsonModel avec le nom d'un item et le nom du fichier .properties.
        
        Args:
            item_name (str): Nom de l'item pour lequel générer le modèle
            properties_name (str): Nom du fichier .properties associé
            specific_suffix (str): Suffixe spécifique pour différencier les variantes
        """
        self.item_name = item_name
        self.properties_name = properties_name
        self.specific_suffix = specific_suffix
        base_output = f"{self.properties_name}_from_{self.item_name}"
        self.output_name = f"{base_output}_{specific_suffix}" if specific_suffix else base_output
        # Vérification des conflits de nom avec JsonModel
        if self.output_name in JsonModel._file_names and JsonModel._file_names[self.output_name] != Path(self.output_name):
            raise JsonModelError(self, f"Un modèle JSON avec le même nom '{self.output_name}' existe déjà : {JsonModel._file_names[self.output_name]}")
        JsonModel._file_names[self.output_name] = Path(self.output_name)
        if organization is None:
            self.organization = Organization.get_organization(self.output_name)
        else:
            self.organization = organization
    
    @classmethod
    def getGenericJsonModel(cls, item_name: str, properties_name: str, specific_suffix: str = "", organization=None) -> 'GenericJsonModel':
        """
        Récupère ou crée une instance de GenericJsonModel pour la combinaison donnée.
        Args:
            item_name (str): Nom de l'item
            properties_name (str): Nom du fichier .properties
            specific_suffix (str): Suffixe spécifique
            organization (Organization | None): Organisation à utiliser
        Returns:
            GenericJsonModel: Instance unique pour cette combinaison
        """
        key = (item_name, properties_name, specific_suffix)
        if key not in cls._instances:
            cls._instances[key] = cls(item_name, properties_name, specific_suffix, organization)
        return cls._instances[key]
    
    def convert(self, texture_override: str | None = None) -> str:
        """
        Génère un modèle JSON générique pour l'item.
        
        Args:
            texture_override (str | None): Texture à utiliser pour le modèle
            
        Returns:
            str: Référence au modèle généré
        """
        if texture_override is None:
            raise JsonModelError(self, "Une texture est requise pour générer un modèle générique")
        
        # Création du modèle
        model_data = {
            "parent": f"minecraft:item/{self.item_name}",
            "textures": {
                "layer0": texture_override
            }
        }
        
        # Création du dossier de sortie
        output_path = self.organization.get_item_model_path(f"{self.output_name}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Sauvegarde du fichier
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(model_data, f, indent=2)
        return self.organization.get_item_model_ref(f"{self.output_name}.json")

class Organization:
    file_mapping = []
    file_mapping_regex = []
    def __init__(self, mapping: dict = None, isRegex: bool = False):
        if mapping is None:
            self.original_path = ""
            self.target_namespace = "default"
            self.target_ressource_root_relative_path = "."
            self.isRegex = False
            return
        required_keys = [
            "original_path",
            "target_namespace",
            "target_ressource_root_relative_path"
        ]
        for key in required_keys:
            if key not in mapping:
                raise ValueError(f"Missing required key: '{key}' in mapping")
        self.original_path = mapping["original_path"]
        self.target_namespace = mapping["target_namespace"]
        self.target_ressource_root_relative_path = mapping["target_ressource_root_relative_path"]
        self.isRegex = isRegex

    def basic_get_ref(self, filename: str):
        return self.target_namespace + ":" + str(Path(self.target_ressource_root_relative_path) / Path(filename).stem).replace('\\', '/').replace('//', '/').rstrip('/')

    def get_equipment_def_path(self, filename):
        return OUTPUT_PATH / "assets" / self.target_namespace / "equipment" / self.target_ressource_root_relative_path / filename

    def get_equipment_def_ref(self, filename):
        return self.basic_get_ref(filename)

    def get_item_def_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "items" / self.target_ressource_root_relative_path / filename

    def get_item_def_ref(self, filename: str):
        return self.basic_get_ref(filename)

    def get_texture_item_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "textures/item" / self.target_ressource_root_relative_path / filename

    def get_texture_item_ref(self, filename: str):
        return self.target_namespace + ":" + str(Path("item") / Path(self.target_ressource_root_relative_path) / Path(filename).stem).replace('\\', '/').replace('//', '/').rstrip('/')

    def get_texture_equip_humanoid_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "textures/entity/equipment/humanoid" / self.target_ressource_root_relative_path / filename

    def get_texture_equip_humanoid_ref(self, filename: str):
        return self.basic_get_ref(filename)

    def get_texture_equip_humanoid_leggings_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "textures/entity/equipment/humanoid_leggings" / self.target_ressource_root_relative_path / filename

    def get_texture_equip_humanoid_leggings_ref(self, filename: str):
        return self.basic_get_ref(filename)

    def get_texture_equip_wings_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "textures/entity/equipment/wings" / self.target_ressource_root_relative_path / filename

    def get_texture_equip_wings_ref(self, filename: str):
        return self.basic_get_ref(filename)

    def get_item_model_path(self, filename: str):
        return OUTPUT_PATH / "assets" / self.target_namespace / "models/item" / self.target_ressource_root_relative_path / filename

    def get_item_model_ref(self, filename: str):
        return self.target_namespace + ":" + str(Path("item") / Path(self.target_ressource_root_relative_path) / Path(filename).stem).replace('\\', '/').replace('//', '/').rstrip('/')

    def match(self, path: str) -> bool:
        from pathlib import Path
        pack_hb = Path("PACK_HB").resolve()
        abs_path = Path(path).resolve()
        try:
            rel_path = abs_path.relative_to(pack_hb)
        except ValueError:
            return False
        def canonical(p):
            return str(p).replace('\\', '/').replace('//', '/').rstrip('/')
        canon_rel = canonical(rel_path)
        canon_orig = canonical(self.original_path)
        if self.isRegex:
            return re.fullmatch(canon_orig, canon_rel) is not None
        else:
            return canon_rel == canon_orig

    @staticmethod
    def get_organization(primary_path: str, secondary_path: str = None):
        # Recherche dans file_mapping_regex
        for org in Organization.file_mapping_regex:
            if org.match(primary_path):
                return org
        # Recherche dans file_mapping
        for org in Organization.file_mapping:
            if org.match(primary_path):
                return org
        # Si rien trouvé et secondary_path fourni
        if secondary_path is not None:
            for org in Organization.file_mapping_regex:
                if org.match(secondary_path):
                    return org
            for org in Organization.file_mapping:
                if org.match(secondary_path):
                    return org
        # Si rien trouvé, retourne une Organization vide
        return Organization()
    
    def __eq__(self, other: 'Organization'):
        return self.target_namespace == other.target_namespace and self.target_ressource_root_relative_path == other.target_ressource_root_relative_path
    
    def __ne__(self, other: 'Organization'):
        return not self.__eq__(other)

# Initialisation statique des mappings à partir de organization.json
with open('organization.json5', 'r', encoding='utf-8') as f:
    data = json5.load(f)
    Organization.file_mapping = [Organization(obj, False) for obj in data.get('file_mapping', [])]
    Organization.file_mapping_regex = [Organization(obj, True) for obj in data.get('file_mapping_regex', [])]

class CIT:
    """
    Classe représentant un fichier CIT (Custom Item Textures) d'OptiFine.
    
    Attributes:
        # Attributs généraux
        property_file_path (Path): Chemin vers le fichier .properties
        raw_properties (dict[str, str]): Dictionnaire contenant les propriétés brutes du fichier
        properties (dict[str, str]): Dictionnaire contenant les propriétés normalisées du fichier
        original_json_model_files_paths (dict[str, Path | None]): Dictionnaire contenant les chemins vers les fichiers modèle JSON originaux
        original_png_texture_files_paths (dict[str, Path | None]): Dictionnaire contenant les chemins vers les fichiers texture PNG originaux
        cit_name (str): Nom du fichier CIT sans extension
        # (model_ref supprimé)
        stack_size_threshold: dict[Path, int] = {}
        item_list: list[str] | None = None
        
        # Attributs de validation
        has_items_property: bool
        has_unspported_specific_texture_property: bool
        has_custom_name: bool
        has_custom_data_property: bool
        has_stack_size: bool
        has_invalid_stack_size: bool
        has_invalid_stack_size_group: bool
        model_file_not_found: bool
        texture_file_not_found: bool
        json_model_error: ConversionError | None
        
        # Attributs de classe pour le suivi des conversions
        cit_with_missing_items: list[Path] = []
        cit_has_specific_texture_property: list[Path] = []
        cit_has_specific_model_property: list[Path] = []
        cit_model_file_not_found: list[Path] = []
        cit_texture_file_not_found: list[Path] = []
        cit_with_json_model_error: dict[Path, ConversionError] = {}
        cit_with_invalid_stack_size: list[Path] = []
        cit_with_invalid_stack_size_group: list[Path] = []
        cit_with_invalid_type: list[Path] = []
        has_texture_dot: bool
        has_model_dot: bool
        has_unspported_specific_model_property: bool
        has_invalid_type: bool
        conversions: list
        cit_nbt_orphelin: list[Path] = []
        cit_icon_orphelin: list[Path] = []
    """
    
    # Attributs généraux
    property_file_path: Path
    raw_properties: dict[str, str]
    properties: dict[str, str]
    original_json_model_files_paths: dict[str, Path | None]
    original_png_texture_files_paths: dict[str, Path | None]
    cit_name: str
    # (model_ref supprimé)
    stack_size_threshold: dict[Path, int] = {}
    item_list: list[str] | None = None
    
    # Attributs de validation
    has_items_property: bool
    has_unspported_specific_texture_property: bool
    has_custom_name: bool
    has_custom_data_property: bool
    has_stack_size: bool
    has_invalid_stack_size: bool
    has_invalid_stack_size_group: bool
    model_file_not_found: bool
    texture_file_not_found: bool
    json_model_error: ConversionError | None
    
    # Attributs de classe pour le suivi des conversions
    cit_with_missing_items: list[Path] = []
    cit_has_specific_texture_property: list[Path] = []
    cit_has_specific_model_property: list[Path] = []
    cit_model_file_not_found: list[Path] = []
    cit_texture_file_not_found: list[Path] = []
    cit_with_json_model_error: dict[Path, ConversionError] = {}
    cit_with_invalid_stack_size: list[Path] = []
    cit_with_invalid_stack_size_group: list[Path] = []
    cit_with_invalid_type: list[Path] = []
    has_texture_dot: bool
    has_model_dot: bool
    has_unspported_specific_model_property: bool
    has_invalid_type: bool
    conversions: list
    cit_nbt_orphelin: list[Path] = []
    cit_icon_orphelin: list[Path] = []
    
    def __init__(self, property_file_path: str | Path):
        """
        Initialise une instance de CIT avec le chemin vers un fichier .properties.
        
        Args:
            property_file_path (str | Path): Chemin vers le fichier .properties
        """
        self.property_file_path = Path(property_file_path)
        self.cit_name = self.property_file_path.stem
        self.raw_properties = read_properties_file(self.property_file_path)
        self.properties = self.normalize_properties()
        self.properties_keys_validations()
        self.properties_values_validations()
        
        # Initialisation de item_list si has_items est vrai
        if self.has_items_property:
            self.item_list = self.properties['items'].split(' ')
        
        # Initialisation de conversions
        self.conversions = []
        
        # Initialisation de original_components (ne garde que les clés commençant par 'components')
        self.original_components = {k: v for k, v in self.properties.items() if k.startswith("components")}
        
        # Partial reproduction of _nbt condition in CIT.convert()
        self.organization = None
        if self.cit_name.endswith("_nbt"):
            base_name = self.cit_name[:-4]
            base_file = self.property_file_path.parent / f"{base_name}.properties"
            if base_file.exists():
                self.organization = Organization.get_organization(base_file)
        else:
            self.organization = Organization.get_organization(self.property_file_path)
    
    @classmethod
    def get_all_cits(cls) -> list['CIT']:
        """
        Crée une liste de tous les objets CIT à partir des fichiers .properties trouvés.
        
        Returns:
            list[CIT]: Liste de tous les objets CIT créés
        """
        return [cls(property_file) for property_file in get_all_cit_properties()]
    
    @classmethod
    def convert_all_cits(cls) -> None:
        """
        Convertit tous les objets CIT trouvés.
        
        Pour chaque CIT, appelle la méthode convert qui vérifie d'abord si la conversion
        peut être effectuée automatiquement.
        """
        # Nettoyage du répertoire de sortie
        clean_output_directory()
        
        all_cits = cls.get_all_cits()
        cit_by_name: dict[str, list[Path]] = {}
        cit_to_convert = all_cits
        for cit in [e for e in all_cits if not e.organization is None]:
            iden_key = "Origninal name: " + cit.cit_name + " - Target namespace: " + cit.organization.target_namespace + " - Target ressource root relative path: " + cit.organization.target_ressource_root_relative_path
            if iden_key not in cit_by_name:
                cit_by_name[iden_key] = [cit.property_file_path]
            else:
                cit_to_convert.remove(cit)
                cit_by_name[iden_key].append(cit.property_file_path)
        duplicated_cit_names = {name: paths for name, paths in cit_by_name.items() if len(paths) > 1}
        for cit in cit_to_convert:
            cit.convert()
        cls.write_conversions(cit_to_convert)
        cls.generate_report(all_cits, duplicated_cit_names)
        
        # Copie du fichier pack.mcmeta
        shutil.copy2('pack.mcmeta', OUTPUT_PATH / 'pack.mcmeta')
    
    @classmethod
    def generate_report(cls, all_cits: list['CIT'], duplicated_cit_names: dict[str, list[Path]]) -> None:
        """
        Génère un rapport Markdown détaillant les CIT qui ne peuvent pas être convertis automatiquement.
        Le rapport est sauvegardé dans le fichier 'conversion_report.md'.
        
        Args:
            all_cits (list[CIT]): Liste de tous les CIT analysés
        """
        report_path = Path('conversion_report.md')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Rapport de conversion des CIT\n\n")
            
            # CIT sans propriété 'items'
            if len(cls.cit_with_missing_items) > 0:
                print(f"Nombre de CIT sans propriété 'items' : {len(cls.cit_with_missing_items)}")
            f.write("## CIT sans propriété 'items'\n\n")
            f.write(f"Nombre total : {len(cls.cit_with_missing_items)}\n\n")
            for path in cls.cit_with_missing_items:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec propriétés texture spécifiques
            if len(cls.cit_has_specific_texture_property) > 0:
                print(f"Nombre de CIT avec des propriétés texture spécifiques : {len(cls.cit_has_specific_texture_property)}")
            f.write("## CIT avec propriétés texture spécifiques\n\n")
            f.write(f"Nombre total : {len(cls.cit_has_specific_texture_property)}\n\n")
            for path in cls.cit_has_specific_texture_property:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec propriétés modèle spécifiques
            if len(cls.cit_has_specific_model_property) > 0:
                print(f"Nombre de CIT avec des propriétés modèle spécifiques : {len(cls.cit_has_specific_model_property)}")
            f.write("## CIT avec propriétés modèle spécifiques\n\n")
            f.write(f"Nombre total : {len(cls.cit_has_specific_model_property)}\n\n")
            for path in cls.cit_has_specific_model_property:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec fichier modèle manquant
            if len(cls.cit_model_file_not_found) > 0:
                print(f"Nombre de CIT avec fichier modèle manquant : {len(cls.cit_model_file_not_found)}")
            f.write("## CIT avec fichier modèle manquant\n\n")
            f.write(f"Nombre total : {len(cls.cit_model_file_not_found)}\n\n")
            for path in cls.cit_model_file_not_found:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec fichier texture manquant
            if len(cls.cit_texture_file_not_found) > 0:
                print(f"Nombre de CIT avec fichier texture manquant : {len(cls.cit_texture_file_not_found)}")
            f.write("## CIT avec fichier texture manquant\n\n")
            f.write(f"Nombre total : {len(cls.cit_texture_file_not_found)}\n\n")
            for path in cls.cit_texture_file_not_found:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec erreur de validation JSON
            if len(cls.cit_with_json_model_error) > 0:
                print(f"Nombre de CIT avec erreur de validation JSON : {len(cls.cit_with_json_model_error)}")
            f.write("## CIT avec erreur de validation JSON\n\n")
            f.write(f"Nombre total : {len(cls.cit_with_json_model_error)}\n\n")
            f.write("| Fichier .properties | Fichier JSON/PNG | Message d'erreur |\n")
            f.write("|-------------------|-----------------|------------------|\n")
            for prop_path, error in cls.cit_with_json_model_error.items():
                if isinstance(error, JsonModelError):
                    file_path = error.json_model.json_path
                else:  # PNGError
                    file_path = error.png.png_path
                f.write(f"| {create_markdown_link(str(report_path), str(prop_path))} | {create_markdown_link(str(report_path), str(file_path))} | {error.message} |\n")
            f.write("\n")
            
            # CIT avec stackSize invalide
            if len(cls.cit_with_invalid_stack_size) > 0:
                print(f"Nombre de CIT avec stackSize invalide : {len(cls.cit_with_invalid_stack_size)}")
            f.write("## CIT avec stackSize invalide\n\n")
            f.write(f"Nombre total : {len(cls.cit_with_invalid_stack_size)}\n\n")
            for path in cls.cit_with_invalid_stack_size:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec groupe de stackSize invalide
            if len(cls.cit_with_invalid_stack_size_group) > 0:
                print(f"Nombre de CIT avec groupe de stackSize invalide : {len(cls.cit_with_invalid_stack_size_group)}")
            f.write("## CIT avec groupe de stackSize invalide\n\n")
            f.write(f"Nombre total : {len(cls.cit_with_invalid_stack_size_group)}\n\n")
            for path in cls.cit_with_invalid_stack_size_group:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # CIT avec cit_name dupliqué
            if len(duplicated_cit_names) > 0:
                print(f"Nombre de CIT avec cit_name dupliqué : {len(duplicated_cit_names)}")
            f.write("## CIT avec cit_name dupliqué\n\n")
            f.write(f"Nombre total de cit_name dupliqués : {len(duplicated_cit_names)}\n\n")
            for cit_name, paths in duplicated_cit_names.items():
                f.write(f"### {cit_name}\n\n")
                f.write(f"Utilisé par {len(paths)} CIT :\n\n")
                for path in paths:
                    f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
                f.write("\n")
            
            # Section CIT avec type invalide
            if len(cls.cit_with_invalid_type) > 0:
                print(f"Nombre de CIT avec type invalide : {len(cls.cit_with_invalid_type)}")
            f.write("## CIT avec type invalide\n\n")
            f.write(f"Nombre total : {len(cls.cit_with_invalid_type)}\n\n")
            for path in cls.cit_with_invalid_type:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")

            # CIT _nbt orphelins
            if len(cls.cit_nbt_orphelin) > 0:
                print(f"Nombre de CIT _nbt orphelins (sans base) : {len(cls.cit_nbt_orphelin)}")
            f.write("## CIT _nbt orphelins (sans base)\n\n")
            f.write(f"Nombre total : {len(cls.cit_nbt_orphelin)}\n\n")
            for path in cls.cit_nbt_orphelin:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")

            # CIT _icon orphelins
            if len(cls.cit_icon_orphelin) > 0:
                print(f"Nombre de CIT _icon orphelins (sans base) : {len(cls.cit_icon_orphelin)}")
            f.write("## CIT _icon orphelins (sans base)\n\n")
            f.write(f"Nombre total : {len(cls.cit_icon_orphelin)}\n\n")
            for path in cls.cit_icon_orphelin:
                f.write(f"- {create_markdown_link(str(report_path), str(path))}\n")
            f.write("\n")
            
            # Résumé
            # f.write("## Résumé\n\n")
            # f.write(f"- Total CIT analysés : {len(all_cits)}\n")
            # f.write(f"- CIT avec cit_name dupliqué : {len(duplicated_cit_names)}\n")
            # f.write(f"- CIT sans propriété 'items' : {len(cls.cit_with_missing_items)}\n")
            # f.write(f"- CIT avec propriétés texture spécifiques : {len(cls.cit_has_specific_texture_property)}\n")
            # f.write(f"- CIT avec fichier modèle manquant : {len(cls.cit_model_file_not_found)}\n")
            # f.write(f"- CIT avec fichier texture manquant : {len(cls.cit_texture_file_not_found)}\n")
            # f.write(f"- CIT avec erreur de validation JSON : {len(cls.cit_with_json_model_error)}\n")
            # f.write(f"- CIT avec stackSize invalide : {len(cls.cit_with_invalid_stack_size)}\n")
            # f.write(f"- CIT avec groupe de stackSize invalide : {len(cls.cit_with_invalid_stack_size_group)}\n")
            # f.write(f"- CIT avec type invalide : {len(cls.cit_with_invalid_type)}\n")
            # f.write(f"- CIT convertibles : {len(all_cits) - len(cls.cit_with_missing_items) - len(cls.cit_has_specific_texture_property) - len(cls.cit_model_file_not_found) - len(cls.cit_texture_file_not_found) - len(cls.cit_with_json_model_error) - len(cls.cit_with_invalid_stack_size) - len(cls.cit_with_invalid_stack_size_group) - len(cls.cit_with_invalid_type)}\n")
            print(f"Nombre de CIT convertibles : {len(all_cits) - len(cls.cit_with_missing_items) - len(cls.cit_has_specific_texture_property) - len(cls.cit_has_specific_model_property) - len(cls.cit_model_file_not_found) - len(cls.cit_texture_file_not_found) - len(cls.cit_with_json_model_error) - len(cls.cit_with_invalid_stack_size) - len(cls.cit_with_invalid_stack_size_group) - len(cls.cit_with_invalid_type) - len(cls.cit_nbt_orphelin) - len(cls.cit_icon_orphelin)}")
    
    def convert(self) -> None:
        base_name = self.cit_name
        if not self.validate_before_conversion():
            return
        # Cas spécial : si cit_name finit par _nbt et qu'un fichier .properties du même nom sans _nbt existe à côté, alors on ne fait que add_conversions et return
        if self.cit_name.endswith("_nbt"):
            base_name = self.cit_name[:-4]
            base_file = self.property_file_path.parent / f"{base_name}.properties"
            if base_file.exists():
                self.add_conversions(
                    Conversion.from_items(
                        self.item_list,
                        self.original_components,
                        self.organization.get_item_def_ref(f"{base_name}.json"),
                        None
                    )
                )
                return
            else:
                CIT.cit_nbt_orphelin.append(self.property_file_path)
                return
        # Cas spécial : si cit_name finit par _icon et qu'un fichier .properties du même nom sans _icon existe à côté ou dans models, on détecte juste l'orphelin
        if self.cit_name.endswith("_icon"):
            base_name = self.cit_name[:-5]
            base_file_1 = self.property_file_path.parent / f"{base_name}.properties"
            base_file_2 = self.property_file_path.parent.parent / "models" / f"{base_name}.properties"
            if not (base_file_1.exists() or base_file_2.exists()):
                CIT.cit_icon_orphelin.append(self.property_file_path)
                
        # Initialisation de l'organisation pour tous les autres cas
        type_value = self.properties.get('type', '')
        if type_value in ('armor', 'elytra'):
            model_ref = self.convert_equipment(equipment_type=type_value, organization=self.organization)
            # Déterminer le slot d'armure
            slot = None
            is_elytra = False
            if self.item_list:
                for item in self.item_list:
                    if re.match(r".*_helmet$", item):
                        slot = "head"
                        break
                    elif re.match(r".*_chestplate$", item) or item == "elytra":
                        slot = "chest"
                        if item == "elytra" or type_value == "elytra":
                            is_elytra = True
                        break
                    elif re.match(r".*_leggings$", item):
                        slot = "legs"
                        break
                    elif re.match(r".*_boots$", item):
                        slot = "feet"
                        break
            icon_file_1 = self.property_file_path.parent / f"{self.property_file_path.stem}_icon.properties"
            icon_file_2 = self.property_file_path.parent.parent / "icons" / f"{self.property_file_path.stem}_icon.properties"
            if icon_file_1.exists() or icon_file_2.exists():
                target_item_def = self.organization.get_item_def_ref(f"{base_name}.json")
            else:
                target_item_def = None
            self.add_conversions(
                Conversion.from_items(
                    self.item_list,
                    self.original_components,
                    target_item_def,
                    model_ref,
                    slot,
                    is_elytra
                )
            )
            return
        else:
            # Logique actuelle pour type == 'item'
            if not self.has_stack_size:
                # Exécution de la logique de conversion standard
                self.convert_item(base_name, self.organization)
            else:
                # Traitement des CIT avec stackSize
                self.convert_stack_item(base_name, self.organization)
    
    def convert_equipment(self, equipment_type: str = "armor", organization=None) -> None:
        if organization is None:
            organization = Organization.get_organization(self.property_file_path)
        if equipment_type == "elytra":
            layer_path = self.original_png_texture_files_paths.get("")
            if not layer_path:
                return
            convert_layer = PNG.getPNG(layer_path).convert(destination="equip_wings")
            equipment_json = {"layers": {"wings": [{"texture": convert_layer}]}}
            output_path = organization.get_equipment_def_path(f"{self.cit_name}.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(equipment_json, f, indent=2, ensure_ascii=False)
            return organization.get_equipment_def_ref(f"{self.cit_name}.json")
        # Logique armor actuelle
        # Trouver les chemins pour layer_1 et layer_2
        layer1_path = None
        layer2_path = None
        for key, path in self.original_png_texture_files_paths.items():
            if key.endswith("layer_1"):
                layer1_path = path
            elif key.endswith("layer_2"):
                layer2_path = path
        # On doit avoir au moins une des deux
        if not layer1_path and not layer2_path:
            return
        # Conversion PNG pour chaque layer trouvée
        convert_layer_1 = None
        convert_layer_2 = None
        if layer1_path:
            convert_layer_1 = PNG.getPNG(layer1_path).convert(destination="equip_humanoid")
        if layer2_path:
            convert_layer_2 = PNG.getPNG(layer2_path).convert(destination="equip_humanoid_leggings")
        layers = {}
        if convert_layer_2:
            layers["humanoid_leggings"] = [{"texture": convert_layer_2}]
        if convert_layer_1:
            layers["humanoid"] = [{"texture": convert_layer_1}]
        equipment_json = {"layers": layers}
        output_path = organization.get_equipment_def_path(f"{self.cit_name}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(equipment_json, f, indent=2, ensure_ascii=False)
        return organization.get_equipment_def_ref(f"{self.cit_name}.json")

    def convert_item(self, base_name, organization=None):
        if organization is None:
            organization = Organization.get_organization(self.property_file_path)
        model_def = self.convert_specific_cit(organization)
        # Création du fichier JSON final
        if model_def is not None:
            try:
                output_path = organization.get_item_def_path(f"{base_name}.json")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(model_def, f, indent=2)
                self.add_conversions(
                    Conversion.from_items(
                        self.item_list,
                        self.original_components,
                        organization.get_item_def_ref(f"{base_name}.json"),
                        None
                    )
                )
            except (FileNotFoundError, PermissionError) as e:
                self.json_model_error = JsonModelError(None, f"Erreur lors de la création du fichier JSON final : {str(e)}")
                CIT.cit_with_json_model_error[self.property_file_path] = self.json_model_error
    
    def convert_specific_model(self, model_suffix: str, organization=None) -> dict | None:
        """
        Renvoie la définition d'item pour le CIT courant et le suffixe de modèle donné ("" pour le modèle principal).
        Détermine le texture_override et convertit le modèle JSON ou génère un modèle générique.
        Returns:
            dict | None: L'objet du modèle généré, ou None en cas d'erreur
        """
        texture_override = None
        if self.original_png_texture_files_paths.get(model_suffix) is not None:
            try:
                png = PNG.getPNG(self.original_png_texture_files_paths.get(model_suffix))
                texture_override = png.convert()
            except PNGError as e:
                self.json_model_error = e
                CIT.cit_with_json_model_error[self.property_file_path] = e
                return None
        if self.original_json_model_files_paths.get(model_suffix) is not None:
            try:
                json_model = JsonModel.getJsonModel(self.original_json_model_files_paths.get(model_suffix), model_suffix)
                model_ref = json_model.convert(texture_override)
                return {
                    "model": {
                        "type": "model",
                        "model": model_ref
                    }
                }
            except (JsonModelError, PNGError) as e:
                self.json_model_error = e
                CIT.cit_with_json_model_error[self.property_file_path] = e
                return None
        elif self.original_json_model_files_paths.get("") is not None:
            try:
                json_model = JsonModel.getJsonModel(self.original_json_model_files_paths.get(""), model_suffix)
                model_ref = json_model.convert(texture_override)
                return {
                    "model": {
                        "type": "model",
                        "model": model_ref
                    }
                }
            except (JsonModelError, PNGError) as e:
                self.json_model_error = e
                CIT.cit_with_json_model_error[self.property_file_path] = e
                return None
        elif self.original_png_texture_files_paths.get(model_suffix) is not None:
            try:
                generic_model = GenericJsonModel.getGenericJsonModel(self.item_list[0], self.cit_name, model_suffix, organization)
                model_ref = generic_model.convert(texture_override)
                return {
                    "model": {
                        "type": "model",
                        "model": model_ref
                    }
                }
            except (JsonModelError, PNGError) as e:
                self.json_model_error = e
                CIT.cit_with_json_model_error[self.property_file_path] = e
                return None
        return None

    def convert_specific_cit(self, organization=None) -> dict | None:
        """
        Renvoie la définition d'item spécifiquement pour le CIT courant, sans prendre en compte les autres CITs voisins.
        Si l'item est un arc ("bow"), applique la logique spéciale pour les états de tir.
        Si l'item est un bouclier ("shield"), applique la logique spéciale pour les états de blocage.
        """
        if self.item_list and "bow" in self.item_list:
            # suffixes peut contenir des str ou des listes de str
            suffixes = [
                ["bow_standby", "bow"],
                "bow_pulling_0",
                "bow_pulling_1",
                "bow_pulling_2"
            ]
            models = {}
            for suffix in suffixes:
                if isinstance(suffix, list):
                    key = suffix[0]
                    result = None
                    for s in suffix:
                        result = self.convert_specific_model(s, organization)
                        if result is not None:
                            break
                    if result is None:
                        models[key] = {"model": {"type": "model", "model": "item/bow"}}
                    else:
                        models[key] = result
                else:
                    result = self.convert_specific_model(suffix, organization)
                    if result is None:
                        models[suffix] = {"model": {"type": "model", "model": "item/bow"}}
                    else:
                        models[suffix] = result
            return {
                "model": {
                    "type": "condition",
                    "on_false": models["bow_standby"]["model"],
                    "on_true": {
                        "type": "range_dispatch",
                        "entries": [
                            {**models["bow_pulling_1"], "threshold": 0.65},
                            {**models["bow_pulling_2"], "threshold": 0.9}
                        ],
                        "fallback": models["bow_pulling_0"]["model"],
                        "property": "minecraft:use_duration",
                        "scale": 0.05
                    },
                    "property": "minecraft:using_item"
                }
            }
        elif self.item_list and "shield" in self.item_list:
            retour_blocking = self.convert_specific_model("shield_blocking", organization)
            retour_normal = self.convert_specific_model("", organization)

            # Valeurs par défaut si None
            if retour_blocking is None:
                retour_blocking = {
                    "model": {
                        "type": "minecraft:special",
                        "base": "minecraft:item/shield_blocking",
                        "model": {"type": "minecraft:shield"}
                    }
                }
            else:
                retour_blocking = {
                    "model": {
                        "type": "minecraft:special",
                        "base": retour_blocking["model"]["model"],
                        "model": {"type": "minecraft:shield"}
                    }
                }
            if retour_normal is None:
                retour_normal = {
                    "model": {
                        "type": "minecraft:special",
                        "base": "minecraft:item/shield",
                        "model": {"type": "minecraft:shield"}
                    }
                }
            else:
                retour_normal = {
                    "model": {
                        "type": "minecraft:special",
                        "base": retour_normal["model"]["model"],
                        "model": {"type": "minecraft:shield"}
                    }
                }
            return {
                "model": {
                    "type": "minecraft:condition",
                    "on_false": retour_normal["model"],
                    "on_true": retour_blocking["model"],
                    "property": "minecraft:using_item"
                }
            }
        else:
            return self.convert_specific_model("", organization)
    
    def validate_before_conversion(self) -> bool:
        """
        Vérifie si la conversion peut être effectuée automatiquement.
        
        Returns:
            bool: True si la conversion peut être effectuée, False sinon
        """
        # Validation du type doit être la première
        if self.has_invalid_type:
            CIT.cit_with_invalid_type.append(self.property_file_path)
            return False
        
        if not self.has_items_property:
            CIT.cit_with_missing_items.append(self.property_file_path)
            return False
        
        if self.has_unspported_specific_texture_property:
            CIT.cit_has_specific_texture_property.append(self.property_file_path)
            return False
        
        if self.has_unspported_specific_model_property:
            CIT.cit_has_specific_model_property.append(self.property_file_path)
            return False
        
        if self.model_file_not_found:
            CIT.cit_model_file_not_found.append(self.property_file_path)
            return False
        
        if self.texture_file_not_found:
            CIT.cit_texture_file_not_found.append(self.property_file_path)
            return False
        
        if self.has_invalid_stack_size:
            CIT.cit_with_invalid_stack_size.append(self.property_file_path)
            return False
        
        if self.has_invalid_stack_size_group:
            CIT.cit_with_invalid_stack_size_group.append(self.property_file_path)
            return False
        
        return True
    
    def normalize_properties(self) -> dict[str, str]:
        """
        Normalise les propriétés du fichier pour les rendre plus standard.
        
        Règles de normalisation :
        - Si le champ 'type' n'existe pas, il est ajouté avec la valeur 'item'
        - Si le champ 'type' existe avec la valeur 'default', il est changé en 'item'
        - Si le champ 'matchItems' existe, il est renommé en 'items'
        - Si la valeur de 'items' commence par 'minecraft:', ce préfixe est supprimé
        
        Returns:
            dict[str, str]: Dictionnaire des propriétés normalisées
        """
        normalized = self.raw_properties.copy()
        
        # Si le champ 'type' n'existe pas, on l'ajoute avec la valeur 'item'
        if 'type' not in normalized:
            normalized['type'] = 'item'
        # Si le champ 'type' existe avec la valeur 'default', on le change en 'item'
        elif normalized['type'] == 'default':
            normalized['type'] = 'item'
        
        # Si le champ 'matchItems' existe, on le renomme en 'items'
        if 'matchItems' in normalized:
            normalized['items'] = normalized.pop('matchItems')
        
        # Si la valeur de 'items' commence par 'minecraft:', on supprime ce préfixe
        if 'items' in normalized and normalized['items'].startswith('minecraft:'):
            normalized['items'] = normalized['items'][10:]  # Supprime 'minecraft:'
        
        return normalized
    
    def properties_keys_validations(self) -> None:
        """
        Effectue les validations sur les clés des propriétés.
        
        Validations effectuées :
        - Vérifie la présence de la propriété 'items'
        - Vérifie la présence de la propriété 'texture'
        - Vérifie la présence de la propriété 'model'
        - Vérifie la présence d'une propriété commençant par 'texture.' (et si non supporté)
        - Vérifie la présence d'une propriété commençant par 'model.'
        - Vérifie la présence de la propriété 'components.custom_name'
        - Vérifie la présence de la propriété 'components.custom_data' ou d'une propriété commençant par 'components.custom_data.'
        - Vérifie la présence de la propriété 'stackSize'
        """
        self.has_items_property = 'items' in self.properties
        supported_complex_items = ["bow", "elytra", "shield"]
        supported_complex_items_regex = [
            r".*_boots$",
            r".*_helmet$",
            r".*_leggings$",
            r".*_chestplate$"
        ]
        items = self.properties['items'].split(' ') if 'items' in self.properties else []

        def is_supported(item):
            if item in supported_complex_items:
                return True
            for pattern in supported_complex_items_regex:
                if re.match(pattern, item):
                    return True
            return False

        self.has_texture_dot = any(key.startswith('texture.') for key in self.properties.keys())
        self.has_unspported_specific_texture_property = (
            (items and not is_supported(items[0])) and
            self.has_texture_dot
        )
        self.has_custom_name = 'components.custom_name' in self.properties
        self.has_custom_data_property = 'components.custom_data' in self.properties or any(key.startswith('components.custom_data.') for key in self.properties.keys())
        self.has_stack_size = 'stackSize' in self.properties
        self.has_model_dot = any(key.startswith('model.') for key in self.properties.keys())
        self.has_unspported_specific_model_property = (
            (items and not is_supported(items[0])) and
            self.has_model_dot
        )
    
    def properties_values_validations(self) -> None:
        """
        Effectue les validations sur les valeurs des propriétés.
        
        Validations effectuées :
        - Vérifie l'existence du fichier modèle JSON référencé
        - Vérifie l'existence des fichiers texture PNG référencés
        - Vérifie le format de la propriété 'stackSize' si présente
        - Vérifie la validité du groupe de stackSize
        """
        # Validation des fichiers modèle JSON (supporte model et model.suffix)
        self.original_json_model_files_paths = {}
        self.model_file_not_found = False
        if 'model' in self.properties:
            model_path = find_file_in_pack(self.property_file_path, self.properties['model'], '.json')
            self.original_json_model_files_paths[""] = model_path
            if model_path is None:
                self.model_file_not_found = True
        for key, value in self.properties.items():
            if key.startswith('model.'):
                suffix = key[6:]
                model_path = find_file_in_pack(self.property_file_path, value, '.json')
                self.original_json_model_files_paths[suffix] = model_path
                if model_path is None:
                    self.model_file_not_found = True
        
        # Validation des fichiers texture (supporte texture et texture.suffix)
        self.original_png_texture_files_paths = {}
        self.texture_file_not_found = False
        if 'texture' in self.properties:
            # Pour la clé 'texture' principale
            tex_path = find_file_in_pack(self.property_file_path, self.properties['texture'], '.png')
            self.original_png_texture_files_paths[""] = tex_path
            if tex_path is None:
                self.texture_file_not_found = True
        # Pour les clés texture.suffix
        for key, value in self.properties.items():
            if key.startswith('texture.'):
                suffix = key[8:]
                tex_path = find_file_in_pack(self.property_file_path, value, '.png')
                self.original_png_texture_files_paths[suffix] = tex_path
                if tex_path is None:
                    self.texture_file_not_found = True
        
        # Validation de stackSize
        self.has_invalid_stack_size = False
        if self.has_stack_size:
            stack_size_value = self.properties['stackSize']
            if '-' in stack_size_value:
                try:
                    min_val, max_val = map(int, stack_size_value.split('-'))
                    CIT.stack_size_threshold[self.property_file_path] = min_val
                except ValueError:
                    self.has_invalid_stack_size = True
            else:
                try:
                    CIT.stack_size_threshold[self.property_file_path] = int(stack_size_value)
                except ValueError:
                    self.has_invalid_stack_size = True
        
        # Validation du groupe de stackSize
        self.has_invalid_stack_size_group = False
        if self.has_stack_size:
            file_name = self.property_file_path.stem
            parent_dir = self.property_file_path.parent
            
            # Vérification si le fichier a un suffixe numérique
            if '_' in file_name:
                base_name = file_name.rsplit('_', 1)[0]
                suffix = file_name.rsplit('_', 1)[1]
                try:
                    int(suffix)  # Vérifie si le suffixe est un nombre
                    # Vérifie si le fichier de base existe ou s'il y a d'autres variantes
                    base_file = parent_dir / f"{base_name}.properties"
                    if not base_file.exists():
                        # Compte le nombre de variantes (sans compter le fichier actuel)
                        variant_count = sum(1 for p in parent_dir.glob(f"{base_name}_*.properties") 
                                         if p != self.property_file_path and 
                                         p.stem.rsplit('_', 1)[1].isdigit())
                        if variant_count == 0:
                            self.has_invalid_stack_size_group = True
                except ValueError:
                    self.has_invalid_stack_size_group = True
            else:
                # Vérifie s'il existe des variantes avec suffixe numérique
                variant_count = sum(1 for p in parent_dir.glob(f"{file_name}_*.properties") 
                                 if p.stem.rsplit('_', 1)[1].isdigit())
                if variant_count == 0:
                    self.has_invalid_stack_size_group = True
        
        # Validation du champ type (doit être 'item' ou 'armor')
        self.has_invalid_type = False
        type_value = self.properties.get('type', '')
        if type_value not in ("item", "armor", "elytra"):
            self.has_invalid_type = True

    def add_conversions(self, conversions: list) -> None:
        self.conversions.extend(conversions)

    def convert_stack_item(self, base_name: str, organization=None):
        if organization is None:
            organization = Organization.get_organization(self.property_file_path)
        parent_dir = self.property_file_path.parent
        base_name = base_name.rsplit('_', 1)[0]
        base_file_path = parent_dir / f"{base_name}.properties"

        # Récupération des variantes
        variants = []
        for variant_path in parent_dir.glob(f"{base_name}_*.properties"):
            try:
                suffix = variant_path.stem.rsplit('_', 1)[1]
                int(suffix)  # Vérifie si le suffixe est un nombre
                variants.append(variant_path)
            except (ValueError, IndexError):
                continue

        if base_file_path.exists():
            variants.append(base_file_path)

        # Suppression du fichier actuel de la liste des variantes
        current_path_canonical = str(self.property_file_path).replace('\\', '/')
        variants = [path for path in variants if str(path).replace('\\', '/') != current_path_canonical]

        # Ajout du fichier actuel à la liste
        variants.append(self.property_file_path)

        # Création des CIT et tri par stack_size_threshold
        cit_variants = []
        for variant_path in variants:
            cit = CIT(variant_path)
            if cit.has_stack_size and not cit.has_invalid_stack_size:
                cit_variants.append(cit)
    
        # Tri des variantes par stack_size_threshold
        cit_variants.sort(key=lambda cit: CIT.stack_size_threshold[cit.property_file_path])

        # Conversion de chaque variante et stockage dans un dictionnaire
        model_defs = {}
        for cit in cit_variants:
            model_def = cit.convert_specific_cit(organization)
            if model_def is not None:
                model_defs[cit.property_file_path] = model_def
        # Création du fichier JSON final pour le groupe
        if len(model_defs) == len(cit_variants):
            try:
                output_path = organization.get_item_def_path(f"{base_name}.json")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                # Création du fichier JSON
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "model": {
                            "type": "range_dispatch",
                            "property": "count",
                            "normalize": False,
                            "entries": [
                                {**model_defs[cit.property_file_path], "threshold": CIT.stack_size_threshold[cit.property_file_path]}
                                for cit in cit_variants
                            ]
                        }
                    }, f, indent=2)
                self.add_conversions(
                    Conversion.from_items(
                        self.item_list,
                        self.original_components,
                        organization.get_item_def_ref(f"{base_name}.json"),
                        None
                    )
                )
            except (FileNotFoundError, PermissionError) as e:
                self.json_model_error = JsonModelError(None, f"Erreur lors de la création du fichier JSON final : {str(e)}")
                CIT.cit_with_json_model_error[self.property_file_path] = self.json_model_error

    @classmethod
    def write_conversions(cls, cits: list['CIT']) -> None:
        all_conversions = []
        for cit in cits:
            for conv in getattr(cit, "conversions", []):
                all_conversions.append(conv.generate())

        # Fusion des conversions similaires
        merged = {}
        for conv in all_conversions:
            key = (
                conv["item"],
                conv.get("target_item_def"),
                tuple(sorted((k, tuple(sorted(v.items()))) for k, v in conv["original_components"].items()))
            )
            if key not in merged:
                merged[key] = conv
            else:
                # Pour chaque champ, on garde la valeur non-None si elle existe
                for field in ["target_armor_def", "target_armor_slot"]:
                    if merged[key].get(field) is None and conv.get(field) is not None:
                        merged[key][field] = conv[field]
        merged_list = list(merged.values())

        with open("conversions.json", "w", encoding="utf-8") as f:
            json.dump(merged_list, f, ensure_ascii=False, indent=2)

class Conversion:
    def __init__(self, item: str, original_components: dict[str, str], target_item_def: str, target_armor_def: str, target_armor_slot: str = None, is_elytra: bool = False):
        self.item = item
        self.original_components = original_components
        self.target_item_def = target_item_def
        self.target_armor_def = target_armor_def
        self.target_armor_slot = target_armor_slot
        self.is_elytra = is_elytra

    def generate(self) -> dict:
        enriched_components = {}
        for key, value in self.original_components.items():
            if isinstance(value, str):
                if value.startswith("iregex:"):
                    enriched_components[key] = {
                        "method": "regex",
                        "value": value[len("iregex:"):]
                    }
                elif value.startswith("ipattern:"):
                    enriched_components[key] = {
                        "method": "regex",
                        "value": value[len("ipattern:"):]
                    }
                else:
                    enriched_components[key] = {
                        "method": "exact",
                        "value": value
                    }
            else:
                enriched_components[key] = {
                    "method": "exact",
                    "value": value
                }
        result = {
            "item": self.item,
            "original_components": enriched_components,
            "target_item_def": self.target_item_def,
            "target_armor_def": self.target_armor_def,
            "target_armor_slot": self.target_armor_slot
        }
        if self.target_armor_def is not None:
            result["is_elytra"] = self.is_elytra
        # Retirer les clés dont la valeur est None
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def from_items(cls, items: list[str], original_components: dict[str, str], target_item_def: str, target_armor_def: str, target_armor_slot: str = None, is_elytra: bool = False) -> list['Conversion']:
        return [cls(item, original_components, target_item_def, target_armor_def, target_armor_slot, is_elytra) for item in items]

if __name__ == '__main__':
    CIT.convert_all_cits()
    # Les prints de statistiques sont maintenant dans generate_report