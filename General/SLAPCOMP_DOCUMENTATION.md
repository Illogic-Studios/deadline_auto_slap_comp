# SLAPCOMP TOOL - DOCUMENTATION TECHNIQUE

**Version:** 2.0 (Refactorisé Décembre 2025)
**Auteur:** Pipeline Team
**But:** Créer automatiquement des comps Nuke à partir de render layers Deadline/Prism

---

## 1. ARCHITECTURE

### Fichiers principaux

```
DeadlineRepository/custom/scripts/
├── Jobs/
│   ├── slapIt.py              # Interface interactive (clic droit sur job Deadline)
│   └── autoSlapIt.py          # Mode automatique (sans UI)
├── General/
│   ├── SlapCompCore.py        # Logique métier partagée (CORE)
│   ├── SlapCompUI_Qt.py       # Interface Qt pour sélection layers/versions
│   └── SLAPCOMP_DOCUMENTATION.md  # Ce fichier
└── Submission/SlapComp/
    └── SubmitSlapCompToDeadline.py  # Soumission job Nuke à Deadline
```

### Flux de données

```
USER (sélection job Deadline)
  │
  ▼
slapIt.py
  │
  ├──> SlapCompCore.get_output_dirs(jobs)
  │     │
  │     ├──> Deadline API (jobs, batches, frames, completion)
  │     ├──> Filesystem scan (Prism structure)
  │     └──> Return: Liste de layers/versions disponibles
  │
  ├──> SlapCompUI_Qt.show_slap_comp_dialog(layers)
  │     │
  │     └──> USER sélectionne layers, versions, merge operations, preset
  │           Return: Configuration utilisateur
  │
  └──> SlapCompCore.call_nuke_script(user_selection)
        │
        ├──> Génère script Nuke (.nk)
        ├──> Auto-incrémente version (v001, v002...)
        ├──> Crée structure Prism (Scenefiles/Renders)
        └──> Soumet job à Deadline via SubmitSlapCompToDeadline.py
```

---

## 2. CONVENTIONS DE NOMMAGE CRITIQUES

### RÈGLE IMPORTANTE : Dual Naming System

**Fichiers (.nk, .exr) = SANS nom de projet**
```
CAPS03_SH0230_SlapComp_v001.nk
CAPS03_SH0230_SlapComp_v001.0002.exr
```

**Job Deadline = AVEC nom de projet**
```
VCA_Perlee_2510_CAPS03_SH0230_SlapComp_v001
```

**Implémentation:** `build_prism_slapcomp_paths()` retourne :
- `base_name` : pour fichiers (sans projet)
- `job_name` : pour Deadline (avec projet)

### Structure Prism attendue

```
I:/PROJECT_NAME/03_Production/Shots/SEQUENCE/SHOT/
├── Scenefiles/Compo/SlapComp/
│   └── SEQ_SHOT_SlapComp_v001.nk
└── Renders/
    ├── 3dRender/LAYER/vXXX/beauty/*.exr
    └── 2dRender/SlapComp/v001/
        └── SEQ_SHOT_SlapComp_v001.%04d.exr
```

---

## 3. FONCTIONS CLÉS (SlapCompCore.py)

### 3.1 Détection et Parsing

#### `extract_prism_from_filesystem_path(directory)`
**But:** Extraire métadonnées Prism depuis un chemin filesystem
**Entrée:** `I:/VCA_Perlee_2510/03_Production/Shots/CAPS03/SH0230/Renders/3dRender/BG/v001`
**Sortie:**
```python
{
    'project': 'VCA_Perlee_2510',
    'sequence': 'CAPS03',
    'shot': 'SH0230',
    'shot_path': 'I:/VCA_Perlee_2510/03_Production/Shots/CAPS03/SH0230'
}
```

#### `extract_prism_from_job_name(job)`
**But:** Extraire métadonnées depuis nom de job Deadline (fallback)
**Pattern:** `PROJECT_SEQUENCE-SHOT_LAYER_vVERSION`
**Exemple:** `VCA_Perlee_2510_CAPS03-SH0230_BG_v001_render`

#### `get_prism_info_smart(job, output_dirs)`
**But:** Wrapper intelligent - essaie filesystem d'abord, fallback sur job name
**Usage:** Toujours utiliser cette fonction pour robustesse

#### `detect_image_sequence_info(directory)`
**But:** Scanner un dossier pour détecter séquences d'images
**Détecte:** Nom de fichier, frame range, padding, total frames
**Pattern supportés:** `*.exr`, `*.dpx`, `*.png`, `*.jpg`, `*.tif`

### 3.2 Versioning

#### `get_existing_slapcomp_versions(shot_path, sequence, shot)`
**But:** Lister toutes les versions existantes de SlapComp pour un shot
**Retour:** `['v001', 'v002', 'v003']`

#### `get_next_version_number(existing_versions)`
**But:** Calculer prochain numéro de version
**Exemple:** `['v001', 'v002']` → retourne `3`

### 3.3 Agrégation Deadline

#### `group_high_prio_and_render_jobs(jobs)`
**But:** Grouper jobs Deadline par base name + version
**Exemple:**
```
VCA_Project_CAPS01_SH0100_CHARS_v005_high_prio
VCA_Project_CAPS01_SH0100_CHARS_v005_render
↓
Groupés ensemble comme "CHARS v005"
```

#### `get_combined_job_completion(jobs)`
**But:** Calculer complétion combinée de plusieurs jobs (high_prio + render)
**Retour:**
```python
{
    'status': 'Completed',      # Completed / Active / Failed
    'completion': 100,           # Pourcentage 0-100
    'completed_frames': 80,
    'total_frames': 80
}
```

**IMPORTANT - Vérification Filesystem:**
Si `total_completed == 0` mais jobs "Completed", le code vérifie automatiquement le filesystem avec `detect_image_sequence_info()` pour obtenir la vraie complétion.

### 3.4 Génération Nuke Script

#### `call_nuke_script(output_info, department, project, preset_name)`
**But:** Point d'entrée principal - génère .nk et soumet à Deadline
**Processus:**
1. Parse Prism info depuis `output_info[0]['directory']`
2. Détermine version (auto-increment si existe)
3. Appelle `build_prism_slapcomp_paths()` pour chemins
4. Génère script Nuke avec `generate_nuke_script()`
5. Crée dossiers si nécessaire
6. Écrit fichier .nk
7. Soumet à Deadline avec `submit_to_deadline()`

#### `generate_nuke_script(output_info, render_path, render_filename, first_frame, last_frame)`
**But:** Génère le code Python du script Nuke
**Contenu:**
- Configuration root node (frame range, format, colorspace)
- Nodes Read (un par layer, positionnés horizontalement)
- Nodes Merge (merge operations configurables)
- Node Write (output final)
- **Node Graph Layout:** Espacement automatique (200px horizontal, 100px vertical)

### 3.5 Soumission Deadline

#### `submit_to_deadline(job_name, scenefile_path, render_dir, first_frame, last_frame, dependencies)`
**But:** Créer et soumetir job Nuke à Deadline
**Propriétés job:**
- `ChunkSize=5` (5 frames par task)
- `ConcurrentTasks=2` (2 tasks max simultanés)
- `Priority=50`
- `Pool=nuke`
- `Group=comp`
- **Dependencies:** Job attend automatiquement si source renders incomplets

---

## 4. INTERFACE UTILISATEUR (SlapCompUI_Qt.py)

### Composants Qt

```python
QTableWidget avec colonnes:
- Layer Name (QLabel)
- Include (QCheckBox)
- Version (QComboBox avec toutes versions disponibles)
- Completion % (QLabel + QProgressBar)
- Merge Operation (QComboBox: over, plus, multiply, screen, etc.)
```

### Presets

**Fichier:** `C:/Users/<user>/slapcomp_presets.json`

**Format:**
```json
{
  "Project preset": {
    "layer_order": ["BG", "CHARS", "FX", "VEGET"],
    "merge_operations": {
      "BG": "over",
      "CHARS": "over",
      "FX": "plus"
    }
  }
}
```

**Comportement:**
- Layers dans preset → Cochés par défaut, réordonnés selon `layer_order`
- Layers hors preset → **Décochés par défaut**, ajoutés à la fin

### Fonctions clés

#### `group_output_info_for_ui(output_info)`
**But:** Transformer liste plate en structure groupée par layer
**Input:** Liste de dicts (1 par version)
**Output:**
```python
{
    'CHARS': {
        'layer_name': 'CHARS',
        'versions': [
            {'version': 'v001', 'completion_percent': 100, 'directory': '...'},
            {'version': 'v002', 'completion_percent': 50, 'directory': '...'}
        ],
        'project': 'VCA_Perlee_2510',
        'sequence': 'CAPS03',
        'shot': 'SH0230',
        'included': True
    }
}
```

#### `apply_preset_data(layers_dict, preset_data)`
**But:** Appliquer preset (ordre, merge ops, inclusion)
**Effet:** Modifie `layers_dict` in-place

---

## 5. SOUMISSION DEADLINE (SubmitSlapCompToDeadline.py)

### Job Info File

```ini
Plugin=Nuke
Name=VCA_Project_CAPS03_SH0230_SlapComp_v001
BatchName=VCA_Project_CAPS03_SH0230_SlapComp_v001
Department=Compo
Pool=nuke
Group=comp
Priority=50
Frames=1-80
ChunkSize=5
ConcurrentTasks=2
```

### Plugin Info File

```ini
SceneFile=I:/Project/03_Production/.../SlapComp/SEQ_SHOT_SlapComp_v001.nk
Version=15.1
OutputDirectory0=I:/Project/.../Renders/2dRender/SlapComp/v001
WriteNode0=Write1
```

### Dependencies

Si `dependencies` fourni (liste de job IDs), ajoute à job info:
```ini
JobDependencies=673bc123456789abcd,673bc987654321dcba
```

**Comportement:** Job reste en "Pending" jusqu'à ce que tous les jobs source soient "Completed"

---

## 6. WORKFLOW UTILISATEUR

### Mode interactif (slapIt.py)

1. **Sélection job** dans Deadline Monitor
2. **Clic droit** → Scripts → slapIt
3. **UI s'ouvre** avec layers détectés
4. **Utilisateur configure:**
   - Coche/décoche layers
   - Sélectionne versions
   - Change merge operations
   - Applique preset si souhaité
5. **Clique OK**
6. **Script génère:**
   - `.nk` file dans `Scenefiles/Compo/SlapComp/`
   - Version auto-incrémentée (v001, v002...)
   - Job Deadline soumis automatiquement

### Mode automatique (autoSlapIt.py)

1. **Même processus** mais sans UI
2. **Sélection automatique:**
   - Toutes les dernières versions
   - Tous les layers inclus
   - Merge operation par défaut: "over"

---

## 7. GESTION DES ERREURS ET FALLBACKS

### Détection Prism

**Ordre de tentative:**
1. `extract_prism_from_filesystem_path(directory)` ← **Préféré**
2. `extract_prism_from_job_name(job)` ← Fallback
3. Mode non-Prism (paths manuels) ← Dernier recours

### Complétion Frames

**Problème:** Jobs anciens ont `JobCompletedTasks` vide même si "Completed"

**Solution (implémentée):**
```python
if total_completed == 0 and total_frames > 0 and status == 'Completed':
    # Vérifier filesystem
    seq_info = detect_image_sequence_info(output_dir)
    total_frames = seq_info['total_frames']
    total_completed = seq_info['total_frames']
    # Maintenant: 80/80 = 100% au lieu de 0/77 = 0%
```

### Detection Image Sequences

**Stratégie:** Scanner 3 niveaux de profondeur
```
LAYER/vXXX/*.exr          ← Niveau 1
LAYER/vXXX/beauty/*.exr   ← Niveau 2 (PRÉFÉRÉ pour Prism)
LAYER/vXXX/subdir/*.exr   ← Niveau 3
```

---

## 8. CONFIGURATION SYSTÈME

### Prérequis

- **Deadline 10.x** avec Repository network share
- **Nuke 15.x** installé sur render nodes
- **Python 2.7** (Deadline) ou **Python 3.x** (selon config)
- **Qt/PySide2** pour UI

### Paths configurables

**Dans SlapCompCore.py:**
```python
# Ligne 85: Fallback Nuke executable
fallback_path = r"C:/Program Files/Nuke15.1v5/Nuke15.1.exe"

# Ligne 701: Department par défaut
default_department = 'Compo'
```

**Dans SubmitSlapCompToDeadline.py:**
```python
# Ligne 54: Deadline command
deadlinecommand = os.path.join(deadline_bin, 'deadlinecommand.exe')

# Ligne 86: Propriétés job
Pool=nuke
Group=comp
Priority=50
ChunkSize=5
ConcurrentTasks=2
```

---

## 9. DÉPANNAGE

### Problème: Fichiers sauvés au mauvais endroit

**Cause:** Prism info non détecté
**Solution:** Vérifier que `output_info[0]['directory']` contient chemin Prism valide
**Pattern attendu:** `*/03_Production/Shots/SEQUENCE/SHOT/*`

### Problème: 0% completion pour jobs terminés

**Cause:** `JobCompletedTasks` vide dans Deadline API
**Solution:** Code vérifie automatiquement filesystem (depuis v2.0)
**Log à chercher:** `"Jobs marked as Completed but 0/X frames reported, checking filesystem..."`

### Problème: Job dependencies ne fonctionnent pas

**Cause:** `job_id` ou `job_ids` non propagés dans data pipeline
**Vérifier:**
- `group_output_info_for_ui()` inclut ces champs (ligne 1142-1143)
- `SlapCompUI_Qt.get_result()` les passe (ligne 534-535)

### Problème: Preset non appliqué correctement

**Cause:** Format JSON invalide ou clés manquantes
**Vérifier:**
```json
{
  "preset_name": {
    "layer_order": [...],      # OBLIGATOIRE
    "merge_operations": {...}  # OPTIONNEL
  }
}
```

### Problème: Nom de fichier avec nom de projet

**Cause:** Utilisation de `job_name` au lieu de `base_name`
**Solution:** `build_prism_slapcomp_paths()` retourne les deux - utiliser `base_name` pour fichiers

---

## 10. MAINTENANCE ET ÉVOLUTION

### Ajout d'un nouveau layer pattern

**Fichier:** `SlapCompCore.py` ligne ~160
**Fonction:** `extract_layer_from_job_name()`

```python
LAYER_PATTERNS = [
    r'_([A-Z_]+)_v\d+',           # Pattern standard
    r'_([A-Z][a-z]+)_v\d+',       # Nouveau pattern à ajouter
]
```

### Ajout support Houdini/Husk

**Décommenter et implémenter:**
```python
def convert_padding_to_nuke(pattern):
    """Convertir $F4 (Houdini) ou %04d (Maya) vers #### (Nuke)"""
    # Code à implémenter
```

**Note:** Actuellement inutile car `detect_image_sequence_info()` génère automatiquement les patterns Nuke.

### Ajout nouvelle merge operation

**Fichier:** `SlapCompUI_Qt.py` ligne ~290

```python
merge_combo = QComboBox()
merge_combo.addItems(['over', 'plus', 'multiply', 'screen', 'under', 'NOUVELLE_OP'])
```

### Changement colorspace par défaut

**Fichier:** `SlapCompCore.py` ligne ~1310

```python
root['colorManagement'].setValue('ACES')
root['workingSpaceLUT'].setValue('ACES - ACEScg')
root['int8LUT'].setValue('Utility - sRGB - Texture')
```

### Module reload sans redémarrer Deadline

**Déjà implémenté** dans `slapIt.py`:
```python
import importlib
importlib.reload(SlapCompCore)
importlib.reload(SlapCompUI_Qt)
```

---

## 11. TESTS ET VALIDATION

### Test checklist

- [ ] Job individuel → Détection layers
- [ ] Batch jobs → Grouping correct
- [ ] Job completed ancien → Affiche 100% (filesystem check)
- [ ] Auto-increment version (v001 → v002)
- [ ] Noms fichiers SANS projet
- [ ] Nom job Deadline AVEC projet
- [ ] Dependencies (job pending si source incomplete)
- [ ] Preset application (ordre + exclusion)
- [ ] Node graph layout (pas de overlap)
- [ ] Multiple merge operations

### Logs importants à surveiller

```
=== get_output_dirs: START ===
  Prism info extracted from filesystem path     ← Succès parsing Prism
  Final completion: 80/80 frames = 100%         ← Complétion correcte
  Jobs marked as Completed but 0/77...          ← Filesystem fallback activé

=== group_output_info_for_ui: START ===
  Found X unique layers                         ← Agrégation OK

Génération script Nuke...
  Script Nuke écrit: .../SlapComp/SEQ_SHOT_SlapComp_v001.nk
  Job soumis avec succès: job_id=...
```

---

## 12. RÉFÉRENCES RAPIDES

### Patterns regex Prism

```python
# Filesystem path
r'[\\/](\w+)[\\/]03_Production[\\/]Shots[\\/]([A-Z0-9_]+)[\\/]([A-Z0-9_]+)[\\/]'

# Job name
r'^([^_]+(?:_[^_]+)*)_([A-Z0-9]+)-([A-Z0-9]+)_'
```

### Frame padding Nuke

```python
# Input filesystem: file.0001.exr
# Nuke pattern: file.####.exr
# Ou avec padding custom: file.%04d.exr
```

### Job states Deadline

- `Active` : En cours de render
- `Completed` : Terminé avec succès
- `Failed` : Erreurs
- `Pending` : En attente (dependencies)
- `Suspended` : Mis en pause

---

**FIN DE DOCUMENTATION**

Pour questions ou bugs: Pipeline Team
Dernière mise à jour: Décembre 2025
