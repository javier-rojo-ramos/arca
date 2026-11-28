"""Escritura de las etiquetas MP4 (M4A): lo propio de esta familia.

Este módulo NO depende de Qt ni de la base de datos. Es el escritor de la familia MP4 del
motor de escritura ('tag_writer.py', que hace lo común: el temporal, comprobar que tiene las
etiquetas previstas y sustituir el original; ver su docstring). Solo lo usa el motor.

CÓMO ESCRIBE (docs/MOD_MUSICA.md, «Cómo se escribe en MP4»; acordado con el autor el
28/11/2026, tras mirar sus 291 M4A):
    1. Cada campo, en su átomo ('tag_map.TagField.mp4': ©nam, ©ART, ©alb, ©day, ©gen, aART,
       ©wrt, ©cmt, trkn y disk). Al vaciar un campo se quita su átomo.
    2. Varios valores («Rock; Pop»), en un solo texto, como en ID3v2.3: las aplicaciones de
       Apple, las que más usan M4A, solo enseñan el primero de varios.
    3. La pista y el disco, la pareja de números del formato, con 0 si no hay total.
    4. El género, en ©gen. Al editarlo se quita también el género numérico antiguo ('gnre',
       de iTunes antiguos: lo tienen 160 de los 291 M4A del autor); al vaciarlo, los dos (si
       quedara 'gnre', volvería el valor antiguo).
    5. Lo demás, byte a byte como estaba: los átomos de etiqueta que no se editan (la
       carátula, ©too, los de iTunes como iTunSMPB, el orden del álbum, 'gnre' si no se
       edita el género...) se copian tal cual, porque mutagen, al volver a escribirlos,
       cambiaría alguno sin que se haya editado (pasa 'gnre' a ©gen y la marca de tipo de
       las carátulas «implícita» a JPEG). Se apoya en una parte interna de mutagen
       ('MP4Tags._failed_atoms', lo que mutagen no entiende y devuelve tal cual); si una
       versión nueva la cambiara, la comprobación del paso 7 lo detectaría y no se
       escribiría nada. El orden de los átomos puede cambiar: los editados van primero.
    6. Si no caben en el relleno que hay junto a las etiquetas (178 de los 291 M4A del autor
       no tienen), mutagen agranda la cabecera ('moov'), desplaza el audio ('mdat') y
       corrige las tablas que dicen dónde está cada trozo ('stco', 'co64'); deja relleno
       para la próxima vez. Un M4A sin etiquetas recibe las suyas. No se escriben los MP4
       fragmentados ('moof') ni los que tienen un átomo 'meta' sin etiquetas (muy raros).
    7. Comprueba el temporal (además de lo común, en el motor): que lo editado se lee como se
       pidió (como lo lee el catálogo, 'tags_from_mp4'); que los átomos de etiqueta no
       editados son los de antes, byte a byte; que el resto de la cabecera es igual, salvo
       las posiciones del audio (los capítulos, las tablas de tamaños y tiempos de cada
       pista...), y que cada trozo de audio, leído a través de sus tablas, es idéntico
       aunque esté en otro sitio.

1.1.0 El comentario, con los saltos de línea de Windows («\r\n», como Mp3tag:
      'tag_map.tag_text'; MUS 7.1c).
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.4).

Prueba: la del motor, de punta a punta con M4A mínimos:
    python -m core.audio.tag_writer
"""

__version__ = "1.1.0"
__all__ = ["Mp4Writer"]

# Librerías estándar
import hashlib
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, BinaryIO, ClassVar

# Librerías de terceros
import mutagen
from mutagen.mp4 import MP4, Atoms

# Módulos del proyecto
from core.audio.tag_map import COMMENT, GENRE, MP4_GENRE_NUMBER, PAIR, tag_field, tag_text
from core.audio.tag_reader import AudioTags, tags_from_mp4
from core.audio.tag_set import TagSet
from core.audio.write_base import AudioWriteError, FormatWriter, PreparedWrite

# La etiqueta de esta familia (no hay nada que elegir en las Opciones)
_MP4_TAGS = TagSet(mp4=True)
# Dónde están las etiquetas: lo que hay en 'meta' lo rehace mutagen (las etiquetas y su relleno)
_META_PATH = (b"moov", b"udta", b"meta")
_ILST = b"ilst"
# Las tablas con la posición de cada trozo de audio (cambian si se desplaza el audio): su
# cabecera (versión y número de entradas) y el tamaño de cada entrada
_OFFSET_TABLES: dict[bytes, str] = {b"stco": ">I", b"co64": ">Q"}
_TABLE_HEADER = 8
# Los átomos de arriba que no se comparan tal cual: la cabecera (se compara por partes) y el
# audio (por sus trozos)
_TOP_COMPARED_APART = frozenset({b"moov", b"mdat"})
# Un MP4 fragmentado (no se escribe)
_FRAGMENT = b"moof"
# Bloques de lectura para la huella del audio
_CHUNK_SIZE = 1 << 20


@dataclass(slots=True)
class _Mp4Prepared(PreparedWrite):
    """Lo preparado para escribir un M4A, y lo que se espera encontrar en el temporal."""

    audio: Any  # el MP4 de mutagen, ya con lo editado
    expected_view: AudioTags  # cómo lo leerá el catálogo
    untouched: list[tuple[str, bytes]]  # los átomos de etiqueta no editados, ordenados
    structure: list[tuple[tuple[bytes, ...], bytes]]  # el resto de la cabecera
    audio_digest: str


class Mp4Writer(FormatWriter):
    """La familia MP4: M4A (ver el docstring del archivo)."""

    name: ClassVar[str] = "mp4"

    def handles(self, audio: Any) -> bool:
        return isinstance(audio, MP4)

    def preferred(self, preferred_mp3: TagSet) -> TagSet:
        return _MP4_TAGS

    def prepare(
        self, path: Path, wanted: dict[str, Any], current: TagSet, target: TagSet
    ) -> PreparedWrite | None:
        audio = mutagen.File(path)
        if not isinstance(audio, MP4):
            raise AudioWriteError(f"«{path.name}» ya no es un M4A")
        with path.open("rb") as file:
            atoms = Atoms(file)
            _check_layout(atoms, path)
            items = _tag_atoms(atoms, file)
            structure = _structure(atoms, file)
            audio_digest = _audio_digest(atoms, file)
        if audio.tags is None:
            audio.add_tags()  # un M4A sin etiquetas
        tags = audio.tags
        base_view = tags_from_mp4(tags)
        edited = _edited_atoms(wanted)
        untouched = [item for item in items if item[0] not in edited]
        expected_view = replace(base_view, **_apply(tags, wanted))
        if current == target and expected_view == base_view:
            return None  # ya tenía lo pedido: no se toca
        _keep_untouched(tags, untouched, edited)
        return _Mp4Prepared(
            wanted=wanted,
            current=current,
            target=target,
            audio=audio,
            expected_view=expected_view,
            untouched=sorted(untouched),
            structure=structure,
            audio_digest=audio_digest,
        )

    def save(self, prepared: PreparedWrite, temp: Path) -> None:
        assert isinstance(prepared, _Mp4Prepared)
        prepared.audio.save(temp)

    def verify(self, prepared: PreparedWrite, temp: Path) -> str | None:
        assert isinstance(prepared, _Mp4Prepared)
        written = MP4(temp)
        if written.tags is None:
            return "no tiene etiquetas"
        if tags_from_mp4(written.tags) != prepared.expected_view:
            return "lo escrito no se lee como se pidió"
        edited = _edited_atoms(prepared.wanted)
        with temp.open("rb") as file:
            atoms = Atoms(file)
            untouched = sorted(item for item in _tag_atoms(atoms, file) if item[0] not in edited)
            if untouched != prepared.untouched:
                return "ha cambiado una etiqueta que no se había editado (la carátula...)"
            if _structure(atoms, file) != prepared.structure:
                return "ha cambiado algo de la cabecera que no es de las etiquetas"
            if _audio_digest(atoms, file) != prepared.audio_digest:
                return "el audio no es el mismo"
        return None


# =============================================================================
# Lo editado
# =============================================================================


def _apply(tags: Any, wanted: Mapping[str, Any]) -> dict[str, Any]:
    """Pone lo editado en las etiquetas de mutagen y devuelve cómo lo leerá el catálogo (los
    atributos de 'AudioTags' que cambian).

    Raises:
        ValueError: Si mutagen no lo admite (un número de pista mayor de 65 535).
    """
    expected: dict[str, Any] = {}
    for key, value in wanted.items():
        field = tag_field(key)
        if field.kind == PAIR:
            number, total = value if value is not None else (None, None)
            if number is None:
                tags.pop(field.mp4, None)
            else:
                tags[field.mp4] = [(number, total or 0)]  # 0: sin total
            expected[f"{key}_number"], expected[f"{key}_total"] = number, total
        else:
            if value is None:
                tags.pop(field.mp4, None)
            else:
                # Varios valores, en un texto (paso 2); el comentario, con los saltos de
                # línea de Windows (como Mp3tag)
                tags[field.mp4] = [tag_text(value) if field.kind == COMMENT else value]
            expected[key] = value
    return expected


def _edited_atoms(wanted: Mapping[str, Any]) -> frozenset[str]:
    """Los átomos de lo editado (con 'gnre' si se edita el género), como claves de mutagen
    (el nombre del átomo en Latin-1: «©nam»)."""
    names: set[str] = set()
    for key in wanted:
        field = tag_field(key)
        names.add(field.mp4)
        if field.kind == GENRE:
            names.add(MP4_GENRE_NUMBER)
    return frozenset(names)


def _keep_untouched(tags: Any, untouched: list[tuple[str, bytes]], edited: frozenset[str]) -> None:
    """Que mutagen escriba solo lo editado y copie tal cual los demás átomos (paso 5): se
    quitan de sus etiquetas los no editados y se le dan, en bruto y en el orden del archivo,
    como los que no entiende (los devuelve sin cambiarlos)."""
    for key in [key for key in tags if key not in edited]:
        del tags[key]
    kept: dict[str, list[bytes]] = {}
    for name, payload in untouched:
        kept.setdefault(name, []).append(payload)
    tags._failed_atoms = kept


# =============================================================================
# El archivo
# =============================================================================


def _check_layout(atoms: Atoms, path: Path) -> None:
    """Lo que no se escribe (paso 6).

    Raises:
        AudioWriteError: Si es un MP4 fragmentado o tiene un 'meta' sin etiquetas.
    """
    if any(atom.name == _FRAGMENT for atom in atoms.atoms):
        raise AudioWriteError(f"«{path.name}» es un MP4 fragmentado: no se escribe")
    if _META_PATH in atoms and (*_META_PATH, _ILST) not in atoms:
        raise AudioWriteError(f"«{path.name}» tiene un átomo «meta» sin etiquetas: no se escribe")


def _tag_atoms(atoms: Atoms, file: BinaryIO) -> list[tuple[str, bytes]]:
    """Los átomos de etiqueta del archivo (los hijos de 'ilst'), en su orden: el nombre, como
    clave de mutagen («©nam», «----»), y su contenido en bruto."""
    try:
        ilst = atoms[(*_META_PATH, _ILST)]
    except KeyError:
        return []
    items = []
    for atom in ilst.children:
        complete, payload = atom.read(file)
        if not complete:
            raise AudioWriteError(f"la etiqueta «{atom.name!r}» está cortada")
        items.append((atom.name.decode("latin-1"), payload))
    return items


def _structure(atoms: Atoms, file: BinaryIO) -> list[tuple[tuple[bytes, ...], bytes]]:
    """La cabecera salvo las etiquetas, para comparar antes y después (paso 7): cada átomo
    final de 'moov' (los que no contienen otros) con su contenido (de las tablas de
    posiciones, solo cuántas entradas tienen: las posiciones cambian si se desplaza el
    audio) y los demás átomos de arriba, menos el audio."""
    state: list[tuple[tuple[bytes, ...], bytes]] = []
    for atom in atoms.atoms:
        if atom.name == b"moov":
            state.extend(_leaves(atom, (atom.name,), file))
        elif atom.name not in _TOP_COMPARED_APART:
            state.append(((atom.name,), _payload(atom, file)))
    return state


def _leaves(atom: Any, path: tuple[bytes, ...], file: BinaryIO) -> Iterator[tuple[tuple[bytes, ...], bytes]]:
    """Los átomos finales de 'atom' (ver '_structure'), menos los de las etiquetas."""
    if path[: len(_META_PATH)] == _META_PATH:
        return  # las etiquetas y su relleno: los rehace mutagen
    if atom.children is None:
        payload = _payload(atom, file)
        if atom.name in _OFFSET_TABLES:
            payload = payload[:_TABLE_HEADER]
        yield path, payload
        return
    for child in atom.children:
        yield from _leaves(child, (*path, child.name), file)


def _payload(atom: Any, file: BinaryIO) -> bytes:
    """El contenido de un átomo.

    Raises:
        AudioWriteError: Si el archivo está cortado.
    """
    complete, payload = atom.read(file)
    if not complete:
        raise AudioWriteError(f"el átomo «{atom.name!r}» está cortado")
    return payload


def _audio_digest(atoms: Atoms, file: BinaryIO) -> str:
    """La huella del audio: cada trozo ('chunk') de cada pista, leído donde dicen sus tablas
    (paso 7), en orden. Igual antes y después aunque el audio se haya desplazado.

    Raises:
        AudioWriteError: Si una pista no tiene sus tablas o no cuadran.
    """
    digest = hashlib.blake2b(digest_size=16)
    for number, trak in enumerate(atoms[b"moov"].findall(b"trak")):
        digest.update(f"pista {number}".encode())
        for offset, size in _chunks(trak, file):
            digest.update(struct.pack(">Q", size))
            file.seek(offset)
            remaining = size
            while remaining:
                data = file.read(min(remaining, _CHUNK_SIZE))
                if not data:
                    raise AudioWriteError("el audio está cortado")
                digest.update(data)
                remaining -= len(data)
    return digest.hexdigest()


def _chunks(trak: Any, file: BinaryIO) -> Iterator[tuple[int, int]]:
    """Dónde está cada trozo de audio de una pista y cuánto ocupa: sus posiciones ('stco' o
    'co64'), cuántas muestras lleva cada uno ('stsc') y el tamaño de cada muestra ('stsz').

    Raises:
        AudioWriteError: Si le falta una tabla o no cuadran.
    """
    try:
        table = trak[b"mdia", b"minf", b"stbl"]
    except KeyError:
        raise AudioWriteError("una pista no tiene sus tablas de audio") from None
    sizes = _sample_sizes(_table(table, b"stsz", file))
    runs = _samples_per_chunk(_table(table, b"stsc", file))
    offsets = _chunk_offsets(table, file)
    sample = 0
    run = 0
    for chunk, offset in enumerate(offsets, start=1):
        while run + 1 < len(runs) and runs[run + 1][0] <= chunk:
            run += 1
        count = runs[run][1] if runs else 0
        if sample + count > len(sizes):
            raise AudioWriteError("las tablas de audio no cuadran")
        yield offset, sum(sizes[sample : sample + count])
        sample += count
    if sample != len(sizes):
        raise AudioWriteError("las tablas de audio no cuadran")


def _table(stbl: Any, name: bytes, file: BinaryIO) -> bytes:
    """El contenido de una tabla de 'stbl'.

    Raises:
        AudioWriteError: Si no la tiene.
    """
    atom = next(stbl.findall(name), None)
    if atom is None:
        raise AudioWriteError(f"una pista no tiene su tabla «{name.decode()}»")
    return _payload(atom, file)


def _sample_sizes(data: bytes) -> list[int]:
    """El tamaño de cada muestra ('stsz': uno común, o uno por muestra)."""
    common, count = struct.unpack(">2I", data[4:12])
    if common:
        return [common] * count
    return list(struct.unpack(f">{count}I", data[12 : 12 + 4 * count]))


def _samples_per_chunk(data: bytes) -> list[tuple[int, int]]:
    """Las rachas de 'stsc': (primer trozo, muestras por trozo), desde ese trozo."""
    (count,) = struct.unpack(">I", data[4:8])
    entries = struct.iter_unpack(">3I", data[8 : 8 + 12 * count])
    return [(first, samples) for first, samples, _description in entries]


def _chunk_offsets(stbl: Any, file: BinaryIO) -> list[int]:
    """La posición de cada trozo ('stco', o 'co64' en archivos de más de 4 GB).

    Raises:
        AudioWriteError: Si no tiene ninguna de las dos.
    """
    for name, item in _OFFSET_TABLES.items():
        atom = next(stbl.findall(name), None)
        if atom is not None:
            data = _payload(atom, file)
            (count,) = struct.unpack(">I", data[4:8])
            size = struct.calcsize(item)
            return list(struct.unpack(f">{count}{item[1]}", data[8 : 8 + size * count]))
    raise AudioWriteError("una pista no tiene la posición de su audio («stco»)")
