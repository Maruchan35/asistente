"""arca_invoice.py — ARCA/AFIP integration para Argentina.
Consultas de facturas, CUIT/CUIL lookup y apertura del portal web.
Para emisión de facturas electrónicas: abre el portal y guía al usuario.
AFIP/ARCA no tiene API pública libre para emisión — se requiere certificado digital."""
from __future__ import annotations
import json, re, urllib.parse, urllib.request, urllib.error, webbrowser
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_keys() -> dict:
    p = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_conf() -> dict:
    p = BASE_DIR / "config" / "arca_config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_conf(cfg: dict):
    p = BASE_DIR / "config" / "arca_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def _get(url: str, timeout: int = 10, headers: dict | None = None) -> dict | str:
    req = urllib.request.Request(
        url, headers=headers or {"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", errors="replace")
            try:
                return json.loads(text)
            except Exception:
                return text
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

def _validate_cuit(cuit: str) -> bool:
    """Validate Argentine CUIT/CUIL format."""
    cuit = re.sub(r"[-\s]", "", cuit)
    if not re.match(r"^\d{11}$", cuit):
        return False
    # Verifying digit algorithm
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total   = sum(int(cuit[i]) * weights[i] for i in range(10))
    rest    = 11 - (total % 11)
    verif   = 0 if rest == 11 else (9 if rest == 10 else rest)
    return verif == int(cuit[10])

def _format_cuit(cuit: str) -> str:
    cuit = re.sub(r"[-\s]", "", cuit)
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}" if len(cuit) == 11 else cuit

# ── Invoice storage ───────────────────────────────────────────────────────────
INV_FILE = BASE_DIR / "config" / "arca_invoices.json"

def _load_invoices() -> list:
    try:
        return json.loads(INV_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_invoices(inv: list):
    INV_FILE.parent.mkdir(parents=True, exist_ok=True)
    INV_FILE.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")

# ══════════════════════════════════════════════════════════════════════════════
def arca_invoice(parameters: dict, player=None) -> str:
    action = parameters.get("action", "portal").lower().strip()

    def log(msg: str):
        if player:
            player.write_log(f"🧾 ARCA/AFIP: {msg}")

    cfg = _load_conf()

    # ── SETUP ─────────────────────────────────────────────────────────────────
    if action in ("setup", "configurar"):
        return (
            "Configuración ARCA/AFIP:\n\n"
            "Para consultas básicas (CUIT, constancias) no necesitás API.\n\n"
            "Para emisión de facturas electrónicas desde código:\n"
            "1. Necesitás un certificado digital de AFIP (certificado.crt + clave_privada.key)\n"
            "2. Solicitalo en: https://auth.afip.gob.ar/contribuyente\n"
            "3. Configurá en config/api_keys.json:\n"
            "   'afip_cuit': 'XX-XXXXXXXX-X'\n"
            "   'afip_cert_path': 'config/afip_cert.crt'\n"
            "   'afip_key_path': 'config/afip_key.key'\n\n"
            "Para uso simple, JARVIS puede abrir el portal web de ARCA."
        )

    # ── PORTAL ────────────────────────────────────────────────────────────────
    if action in ("portal", "abrir", "open"):
        webbrowser.open("https://auth.afip.gob.ar/contribuyente")
        log("Portal ARCA abierto")
        return "Portal de ARCA/AFIP abierto en el navegador."

    # ── EMITIR FACTURA (portal) ───────────────────────────────────────────────
    elif action in ("emitir", "nueva_factura", "create", "facturar"):
        tipo   = parameters.get("tipo", "B").upper()   # A, B, C
        monto  = parameters.get("monto", parameters.get("amount", ""))
        cliente= parameters.get("cliente", parameters.get("client", ""))
        cuit_c = parameters.get("cuit_cliente", "")
        concepto = parameters.get("concepto", parameters.get("description", "Servicio profesional"))

        # Save draft locally
        invoices = _load_invoices()
        draft = {
            "id":        len(invoices) + 1,
            "tipo":      f"Factura {tipo}",
            "monto":     monto,
            "cliente":   cliente,
            "cuit":      cuit_c,
            "concepto":  concepto,
            "fecha":     datetime.now().strftime("%Y-%m-%d %H:%M"),
            "estado":    "borrador",
        }
        invoices.append(draft)
        _save_invoices(invoices)

        # Open AFIP portal for actual invoice emission
        webbrowser.open("https://serviciosweb.afip.gob.ar/genericos/comprobantes/")
        log(f"Factura {tipo} por ${monto} — portal abierto")
        return (
            f"Borrador guardado localmente:\n"
            f"  Tipo: Factura {tipo}\n"
            f"  Cliente: {cliente or 'Sin especificar'}\n"
            f"  CUIT: {_format_cuit(cuit_c) if cuit_c else 'Sin especificar'}\n"
            f"  Monto: ${monto}\n"
            f"  Concepto: {concepto}\n\n"
            "Portal de facturación AFIP abierto en el navegador.\n"
            "La emisión electrónica real requiere certificado digital de AFIP."
        )

    # ── LIST FACTURAS ─────────────────────────────────────────────────────────
    elif action in ("list", "listar", "historial"):
        invoices = _load_invoices()
        if not invoices:
            return "No hay facturas registradas todavía."
        lines = [f"Facturas registradas ({len(invoices)}):"]
        for inv in invoices[-10:]:
            lines.append(
                f"  [{inv.get('id','?')}] {inv.get('tipo','?')} — "
                f"{inv.get('cliente','?')} — ${inv.get('monto','?')} — "
                f"{inv.get('fecha','?')[:10]} ({inv.get('estado','?')})"
            )
        total = sum(float(i.get('monto', 0) or 0) for i in invoices)
        lines.append(f"\n  Total: ${total:,.2f}")
        log(f"{len(invoices)} facturas listadas")
        return "\n".join(lines)

    # ── VALIDAR CUIT ─────────────────────────────────────────────────────────
    elif action in ("validar_cuit", "check_cuit", "cuit"):
        cuit = parameters.get("cuit", parameters.get("value", "")).strip()
        if not cuit:
            return "Especificá cuit con el número a validar."
        cuit_clean = re.sub(r"[-\s]", "", cuit)
        if not _validate_cuit(cuit_clean):
            return f"CUIT/CUIL '{cuit}' es INVÁLIDO (dígito verificador incorrecto o formato incorrecto)."
        formatted = _format_cuit(cuit_clean)
        log(f"CUIT validado: {formatted}")
        return f"CUIT/CUIL {formatted} es VÁLIDO."

    # ── CONSTANCIA ────────────────────────────────────────────────────────────
    elif action in ("constancia", "buscar_cuit", "lookup"):
        cuit = parameters.get("cuit", parameters.get("value", "")).strip()
        if not cuit:
            return "Especificá cuit para buscar la constancia de inscripción."
        cuit_clean = re.sub(r"[-\s]", "", cuit)
        if not _validate_cuit(cuit_clean):
            return f"CUIT '{cuit}' inválido. Verificá el número."
        # Open AFIP constancia page
        constancia_url = f"https://seti.afip.gob.ar/padron-puc-constancia-internet/ConsultaConstanciaAction.do"
        webbrowser.open(constancia_url)
        log(f"Constancia CUIT {_format_cuit(cuit_clean)}")
        return (
            f"CUIT {_format_cuit(cuit_clean)} — página de constancia abierta en el navegador.\n"
            "Ingresá el CUIT para ver los datos de inscripción en AFIP."
        )

    # ── TIPOS DE IVA ─────────────────────────────────────────────────────────
    elif action in ("iva", "alicuotas", "tasas"):
        return (
            "Alícuotas de IVA (Argentina 2024):\n"
            "  Tasa General:        21%\n"
            "  Tasa Diferencial:    10.5%  (bienes de capital, construcción, etc.)\n"
            "  Tasa Reducida:        5%    (medicamentos, libros)\n"
            "  Exento:               0%    (alimentos básicos, educación, salud)\n"
            "  No Gravado:           -     (no aplica IVA)\n\n"
            "Monotributistas emiten Facturas C (sin IVA discriminado).\n"
            "Responsables Inscriptos emiten A/B con IVA discriminado."
        )

    # ── CATEGORÍAS MONOTRIBUTO ────────────────────────────────────────────────
    elif action in ("monotributo", "categorias"):
        webbrowser.open("https://www.afip.gob.ar/monotributo/categorias.asp")
        return (
            "Categorías de Monotributo (2024 — valores aproximados):\n"
            "  A: hasta $68,408/mes  ($7.5M anuales)\n"
            "  B: hasta $101,523/mes\n"
            "  C: hasta $142,536/mes\n"
            "  D-K: escalas superiores\n\n"
            "Página de AFIP con valores actualizados abierta en el navegador."
        )

    # ── VENCIMIENTOS ─────────────────────────────────────────────────────────
    elif action in ("vencimientos", "fechas", "calendario"):
        webbrowser.open("https://www.afip.gob.ar/vencimientos/")
        return "Calendario de vencimientos impositivos abierto en el navegador."

    # ── MARK AS PAID ─────────────────────────────────────────────────────────
    elif action in ("cobrada", "pagar", "mark_paid"):
        inv_id = int(parameters.get("id", parameters.get("invoice_id", 0)))
        invoices = _load_invoices()
        for inv in invoices:
            if inv.get("id") == inv_id:
                inv["estado"] = "cobrada"
                inv["fecha_cobro"] = datetime.now().strftime("%Y-%m-%d")
                _save_invoices(invoices)
                log(f"Factura #{inv_id} marcada como cobrada")
                return f"Factura #{inv_id} marcada como cobrada."
        return f"No se encontró la factura #{inv_id}."

    return (
        f"Acción '{action}' no reconocida. "
        "Usa: portal | emitir | list | validar_cuit | constancia | iva | "
        "monotributo | vencimientos | cobrada | setup"
    )
