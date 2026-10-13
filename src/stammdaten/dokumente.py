"""Ablage von Anhängen: geschützter Speicher, Dateinamen, Größenprüfung."""
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext


class GeschuetzterSpeicher(FileSystemStorage):
    """Dateien liegen außerhalb des Webpfads; Links führen immer über die rechtegeprüfte Download-Ansicht."""

    def url(self, name):
        return reverse("anhang_pfad", args=[name])


def geschuetzter_speicher():
    return GeschuetzterSpeicher()


def ablagepfad(instance, dateiname):
    """Zufälliger Dateiname, damit nichts erraten oder überschrieben werden kann; Originalname bleibt in der Datenbank."""
    endung = os.path.splitext(dateiname)[1].lower()[:10]
    return f"personen/{timezone.now():%Y}/{uuid.uuid4().hex}{endung}"


def groesse_pruefen(datei):
    grenze = settings.DOKUMENT_MAX_MB * 1024 * 1024
    if datei and getattr(datei, "size", 0) > grenze:
        raise ValidationError(
            gettext("Die Datei ist zu groß (höchstens %(mb)s MB).") % {"mb": settings.DOKUMENT_MAX_MB}
        )


def groesse_lesbar(byte):
    if not byte:
        return ""
    from django.utils.formats import number_format

    if byte < 1024:
        return f"{byte} B"
    if byte < 1024 * 1024:
        return f"{number_format(byte / 1024, 0 if byte >= 10 * 1024 else 1)} KB"
    return f"{number_format(byte / 1024 / 1024, 1)} MB"


# Diese Dateiarten darf der Browser direkt anzeigen; alles andere wird nur heruntergeladen.
INLINE_TYPEN = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "text/plain"}
