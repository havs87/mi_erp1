from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import date

DB_NAME = "mi_erp.db"
app = Flask(__name__)
app.secret_key = "tu_clave_supersecreta"  # Cambia esto por una clave más segura en producción

DB_NAME = "mi_erp.db"

# -------------------- INIT DB (crea tablas y siembra ejemplos) --------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 1) USUARIOS (estructura mínima; columnas extra se añaden con ensure_user_columns)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE
        )
    """)

    # 2) CATEGORIAS
    c.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,      -- 'ingreso' o 'egreso'
            nombre TEXT NOT NULL
        )
    """)

    # 3) SUBCATEGORIAS
    c.execute("""
        CREATE TABLE IF NOT EXISTS subcategorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            FOREIGN KEY(categoria_id) REFERENCES categorias(id)
        )
    """)

    # 4) MOVIMIENTOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,                -- 'ingreso' o 'egreso'
            categoria_id INTEGER,
            subcategoria_id INTEGER,
            descripcion TEXT,
            monto REAL,
            FOREIGN KEY(categoria_id) REFERENCES categorias(id),
            FOREIGN KEY(subcategoria_id) REFERENCES subcategorias(id)
        )
    """)

    # 5) PEDIDOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etapa TEXT,
            numero_pedido TEXT,
            fecha TEXT,
            fecha_entrega_propuesta TEXT,
            fecha_entrega_real TEXT,
            motivo_retraso TEXT,
            canal TEXT,
            oc TEXT,
            doc_venta TEXT,
            cliente TEXT,
            descripcion TEXT,
            importe REAL,
            gasto REAL
        )
    """)

    # Crear tabla ingresos
    c.execute("""
        CREATE TABLE IF NOT EXISTS ingresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            monto REAL,
            forma_pago TEXT,
            fecha TEXT,
            depositado INTEGER DEFAULT 0,
            FOREIGN KEY(pedido_id) REFERENCES pedidos(id)
        )
    """)

    conn.commit()

    # 7) Sembrar categorías/subcategorías de ejemplo si están vacías
    #    (solo si no hay ninguna)
    c.execute("SELECT COUNT(*) FROM categorias")
    if (c.fetchone() or [0])[0] == 0:
        c.executemany("INSERT INTO categorias (tipo, nombre) VALUES (?, ?)", [
            ("ingreso", "Ventas"),
            ("ingreso", "Servicios"),
            ("egreso", "Transporte"),
            ("egreso", "Insumos"),
        ])
        conn.commit()

    c.execute("SELECT COUNT(*) FROM subcategorias")
    if (c.fetchone() or [0])[0] == 0:
        # Asumimos IDs 1..4 en el orden insertado arriba
        c.executemany("INSERT INTO subcategorias (categoria_id, nombre) VALUES (?, ?)", [
            (1, "Venta en tienda"),
            (1, "Venta online"),
            (3, "Gasolina"),
            (3, "Mantenimiento"),
        ])
        conn.commit()

    conn.close()

    # 8) Migraciones y usuario admin (cada función abre/cierra su propia conexión)
    ensure_user_columns()
    ensure_admin_user()


# -------------------- MIGRACIÓN SUAVE DE USUARIOS --------------------
def ensure_user_columns():
    """Añade a 'usuarios' las columnas que falten y normaliza valores nulos."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("PRAGMA table_info(usuarios)")
    cols = {row[1] for row in c.fetchall()}

    def add_col(name, ddl):
        if name not in cols:
            c.execute(f"ALTER TABLE usuarios ADD COLUMN {name} {ddl}")

    add_col("password", "TEXT DEFAULT ''")
    add_col("is_admin", "INTEGER DEFAULT 0")
    add_col("mod_pedidos", "INTEGER DEFAULT 1")
    add_col("mod_movimientos", "INTEGER DEFAULT 1")
    add_col("mod_admin", "INTEGER DEFAULT 0")
    add_col("mod_usuarios", "INTEGER DEFAULT 0")

    # Normalizar NULLs a sus defaults
    c.execute("UPDATE usuarios SET password = COALESCE(password, '')")
    c.execute("UPDATE usuarios SET is_admin = COALESCE(is_admin, 0)")
    c.execute("UPDATE usuarios SET mod_pedidos = COALESCE(mod_pedidos, 1)")
    c.execute("UPDATE usuarios SET mod_movimientos = COALESCE(mod_movimientos, 1)")
    c.execute("UPDATE usuarios SET mod_admin = COALESCE(mod_admin, 0)")
    c.execute("UPDATE usuarios SET mod_usuarios = COALESCE(mod_usuarios, 0)")

    conn.commit()
    conn.close()


# -------------------- ADMIN POR DEFECTO --------------------
def ensure_admin_user():
    """Crea o normaliza el usuario Administrador (pass 1812) con todos los permisos."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT id, password FROM usuarios WHERE username=?", ("Administrador",))
    row = c.fetchone()

    if row is None:
        c.execute("""
            INSERT INTO usuarios (username, password, is_admin,
                                  mod_pedidos, mod_movimientos, mod_admin, mod_usuarios)
            VALUES (?, ?, 1, 1, 1, 1, 1)
        """, ("Administrador", "1812"))
    else:
        # Si existe, asegura permisos; conserva contraseña si ya tiene una
        c.execute("""
            UPDATE usuarios
            SET password = CASE WHEN password IS NULL OR password='' THEN '1812' ELSE password END,
                is_admin = 1,
                mod_pedidos = 1,
                mod_movimientos = 1,
                mod_admin = 1,
                mod_usuarios = 1
            WHERE username = ?
        """, ("Administrador",))

    conn.commit()
    conn.close()


# Llamar al inicio del programa
init_db()

# (Opcional: si prefieres, puedes llamar a estas dos aquí, pero ya se invocan dentro de init_db)
# ensure_user_columns()
# ensure_admin_user()


# -------------------- LOGIN --------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user["username"]
            session["user_id"] = user["id"]

            # permisos de módulos
            session["mod_pedidos"] = bool(user["mod_pedidos"])
            session["mod_movimientos"] = bool(user["mod_movimientos"])
            session["mod_admin"] = bool(user["mod_admin"])
            session["mod_usuarios"] = bool(user["mod_usuarios"])

            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Usuario o contraseña incorrectos")

    return render_template("login.html")




# -------------------- DASHBOARD --------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

# -------------------- MOVIMIENTOS --------------------
@app.route("/movimientos")
def movimientos_list():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.tipo, 
               (SELECT nombre FROM categorias WHERE id = m.categoria_id) as categoria,
               (SELECT nombre FROM subcategorias WHERE id = m.subcategoria_id) as subcategoria,
               m.descripcion, m.monto
        FROM movimientos m
        ORDER BY m.id DESC
    """)
    movimientos = c.fetchall()
    conn.close()
    return render_template("movimientos.html", movimientos=movimientos)

@app.route("/movimientos/add", methods=["POST"])
def add_movimiento():
    tipo = request.form["tipo"]
    categoria_id = request.form.get("categoria")
    usar_sub = request.form.get("usar_subcategoria")
    subcategoria_id = request.form.get("subcategoria") if usar_sub else None
    descripcion = request.form["descripcion"]
    monto = request.form["monto"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO movimientos (tipo, categoria_id, subcategoria_id, descripcion, monto) VALUES (?, ?, ?, ?, ?)",
              (tipo, categoria_id, subcategoria_id, descripcion, monto))
    conn.commit()
    conn.close()
    return redirect(url_for("movimientos_list"))

# -------------------- EDITAR MOVIMIENTO --------------------
@app.route("/movimientos/update", methods=["POST"])
def update_movimiento():
    if "user" not in session:
        return redirect(url_for("login"))

    mov_id = request.form["id"]
    categoria_id = request.form.get("categoria_id")
    subcategoria_id = request.form.get("subcategoria_id")
    descripcion = request.form.get("descripcion")
    monto = request.form.get("monto")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if categoria_id:
        c.execute("UPDATE movimientos SET categoria_id=? WHERE id=?", (categoria_id, mov_id))
    if subcategoria_id:
        c.execute("UPDATE movimientos SET subcategoria_id=? WHERE id=?", (subcategoria_id, mov_id))
    if descripcion:
        c.execute("UPDATE movimientos SET descripcion=? WHERE id=?", (descripcion, mov_id))
    if monto:
        c.execute("UPDATE movimientos SET monto=? WHERE id=?", (monto, mov_id))
    conn.commit()
    conn.close()

    return ("", 204)  # Respuesta vacía pero válida


# -------------------- API CATEGORÍAS --------------------
@app.route("/api/categorias/<tipo>")
def get_categorias(tipo):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM categorias WHERE tipo=?", (tipo,))
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route("/api/subcategorias/<int:categoria_id>")
def get_subcategorias(categoria_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM subcategorias WHERE categoria_id=?", (categoria_id,))
    data = c.fetchall()
    conn.close()
    return jsonify(data)


# ==========================
#   PEDIDOS & INGRESOS
# ==========================
from datetime import date, datetime

def _dias_restantes(fecha_str: str):
    try:
        if not fecha_str:
            return None
        hoy = date.today()
        f = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        return (f - hoy).days
    except Exception:
        return None

@app.route("/pedidos")
def pedidos_list():
    # Requiere login y permiso
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_pedidos"):
        return redirect(url_for("dashboard"))

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Traer pedidos (orden por # Pedido desc)
    c.execute("""
        SELECT p.*
        FROM pedidos p
        ORDER BY CAST(p.numero_pedido AS INTEGER) DESC, p.numero_pedido DESC
    """)
    pedidos_rows = c.fetchall()

    # Construir ingresos por pedido + totales + días
    pedidos = []
    ingresos_map = {}
    efectivo_pen = 0
    efectivo_usd = 0

    for p in pedidos_rows:
        pid = p["id"]
        c.execute("""
            SELECT id, pedido_id, monto, forma_pago, fecha, depositado
            FROM ingresos
            WHERE pedido_id=?
            ORDER BY id DESC
        """, (pid,))
        ingresos = c.fetchall()
        ingresos_list = [dict(i) for i in ingresos]
        ingresos_map[pid] = ingresos_list

        # Calcular totales
        total_ingresos = sum((i["monto"] or 0) for i in ingresos_list)
        dias = None
        if p["fecha_entrega_propuesta"]:
            try:
                dias = (date.fromisoformat(p["fecha_entrega_propuesta"]) - date.today()).days
            except Exception:
                dias = None

        # Armar dict
        p_dict = dict(p)
        p_dict["total_ingresos"] = round(total_ingresos, 2)
        p_dict["dias"] = dias
        pedidos.append(p_dict)

        # Calcular efectivo en caja (solo ingresos no depositados)
        for ing in ingresos_list:
            if not ing["depositado"]:
                if (p["moneda"] or "PEN") == "USD":
                    efectivo_usd += ing["monto"] or 0
                else:
                    efectivo_pen += ing["monto"] or 0

    conn.close()

    return render_template(
        "pedidos.html",
        pedidos=pedidos,
        ingresos=ingresos_map,
        today=date.today().isoformat(),
        efectivo_pen=efectivo_pen,
        efectivo_usd=efectivo_usd
    )

# -------------------- NUEVO PEDIDO --------------------
@app.route("/nuevo_pedido", methods=["POST"])
def nuevo_pedido():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_pedidos"):
        return redirect(url_for("dashboard"))

    etapa = "P. Generado"  # por defecto
    numero_pedido = request.form.get("numero_pedido", "").strip()
    fecha = request.form.get("fecha") or date.today().isoformat()
    fecha_entrega_propuesta = request.form.get("fecha_entrega_propuesta") or None
    fecha_entrega_real = request.form.get("fecha_entrega_real") or None
    motivo_retraso = request.form.get("motivo_retraso") or None
    canal = request.form.get("canal") or None
    oc = request.form.get("oc") or None
    doc_venta = request.form.get("doc_venta") or None
    cliente = request.form.get("cliente") or ""
    descripcion = request.form.get("descripcion") or ""
    importe = request.form.get("importe")
    importe = float(importe) if importe not in (None, "",) else None
    gasto = request.form.get("gasto")
    gasto = float(gasto) if gasto not in (None, "",) else 0.0
    moneda = request.form.get("moneda", "PEN")  # PEN por defecto


    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO pedidos
        (etapa, numero_pedido, fecha, fecha_entrega_propuesta, fecha_entrega_real,
         motivo_retraso, canal, oc, doc_venta, cliente, descripcion, importe, gasto, moneda)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (etapa, numero_pedido, fecha, fecha_entrega_propuesta, fecha_entrega_real,
          motivo_retraso, canal, oc, doc_venta, cliente, descripcion, importe, gasto, moneda))
    conn.commit()
    conn.close()
    return redirect(url_for("pedidos_list"))

# -------------------- NUEVO INGRESO --------------------
@app.route("/api/nuevo_ingreso", methods=["POST"])
def api_nuevo_ingreso():
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    if not session.get("mod_pedidos"):
        return jsonify({"ok": False, "error": "Sin permiso"}), 403

    pedido_id = request.form.get("pedido_id")
    monto = request.form.get("monto")
    forma_pago = request.form.get("forma_pago") or ""
    fecha = request.form.get("fecha") or date.today().isoformat()

    try:
        monto = float(monto)
    except Exception:
        return jsonify({"ok": False, "error": "Monto inválido"}), 400

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id FROM pedidos WHERE id=?", (pedido_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"ok": False, "error": "Pedido NO existe"}), 400

    c.execute("""
        INSERT INTO ingresos (pedido_id, monto, forma_pago, fecha, depositado)
        VALUES (?, ?, ?, ?, 0)
    """, (pedido_id, monto, forma_pago, fecha))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})



@app.route("/api/toggle_ingreso", methods=["POST"])
def api_toggle_ingreso():
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    if not session.get("mod_pedidos"):
        return jsonify({"ok": False, "error": "Sin permiso"}), 403

    ingreso_id = request.form.get("ingreso_id")
    valor = request.form.get("valor", "0")
    valor = 1 if str(valor) in ("1", "true", "True") else 0

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE ingresos SET depositado=? WHERE id=?", (valor, ingreso_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/eliminar_ingreso/<int:ingreso_id>", methods=["POST"])
def eliminar_ingreso(ingreso_id):
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    if not session.get("mod_pedidos"):
        return jsonify({"ok": False, "error": "Sin permiso"}), 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM ingresos WHERE id=?", (ingreso_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/eliminar_pedido/<int:pedido_id>", methods=["POST"])
def eliminar_pedido(pedido_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_pedidos"):
        return redirect(url_for("dashboard"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM ingresos WHERE pedido_id=?", (pedido_id,))
    c.execute("DELETE FROM pedidos WHERE id=?", (pedido_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("pedidos_list"))

@app.route("/api/editar_pedido/<int:pedido_id>", methods=["POST"])
def api_editar_pedido(pedido_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_pedidos"):
        return redirect(url_for("dashboard"))

    cliente = request.form.get("cliente") or ""
    descripcion = request.form.get("descripcion") or ""
    fecha_entrega_propuesta = request.form.get("fecha_entrega_propuesta") or None

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        UPDATE pedidos
        SET cliente=?, descripcion=?, fecha_entrega_propuesta=?
        WHERE id=?
    """, (cliente, descripcion, fecha_entrega_propuesta, pedido_id))
    conn.commit()
    conn.close()
    return redirect(url_for("pedidos_list"))






@app.route("/administracion")
def administracion_panel():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_admin"):
        return "Acceso no autorizado", 403
    return render_template("administracion.html")


# -------------------- PERFIL DE USUARIOS --------------------
@app.route("/usuarios")
def perfil_usuarios():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("mod_admin"):
        return "Acceso no autorizado", 403

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    usuarios = c.execute("SELECT * FROM usuarios").fetchall()
    conn.close()

    return render_template("perfil_usuarios.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["POST"])
def nuevo_usuario():
    username = request.form.get("username")
    password = request.form.get("password")
    is_admin = 1 if request.form.get("is_admin") else 0

    # permisos básicos
    mod_pedidos = 1 if request.form.get("mod_pedidos") else 0
    mod_movimientos = 1 if request.form.get("mod_movimientos") else 0
    mod_admin = 1 if request.form.get("mod_admin") else 0
    mod_usuarios = 1 if request.form.get("mod_usuarios") else 0

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO usuarios (username, password, is_admin,
                              mod_pedidos, mod_movimientos, mod_admin, mod_usuarios)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (username, password, is_admin, mod_pedidos, mod_movimientos, mod_admin, mod_usuarios))
    conn.commit()
    conn.close()
    return redirect(url_for("perfil_usuarios"))

@app.route("/usuarios/editar/<int:user_id>", methods=["POST"])
def editar_usuario(user_id):
    username = request.form.get("username")
    password = request.form.get("password")
    is_admin = 1 if request.form.get("is_admin") else 0

    mod_pedidos = 1 if request.form.get("mod_pedidos") else 0
    mod_movimientos = 1 if request.form.get("mod_movimientos") else 0
    mod_admin = 1 if request.form.get("mod_admin") else 0
    mod_usuarios = 1 if request.form.get("mod_usuarios") else 0

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        UPDATE usuarios
        SET username=?, password=?, is_admin=?,
            mod_pedidos=?, mod_movimientos=?, mod_admin=?, mod_usuarios=?
        WHERE id=?
    """, (username, password, is_admin,
          mod_pedidos, mod_movimientos, mod_admin, mod_usuarios, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("perfil_usuarios"))

@app.route("/usuarios/eliminar/<int:user_id>", methods=["POST"])
def eliminar_usuario(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("perfil_usuarios"))


# -------------------- CATEGORIAS Y SUBCATEGORIAS --------------------
@app.route("/categorias")
def categorias_list():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    categorias = c.execute("SELECT * FROM categorias").fetchall()
    subcategorias = c.execute("SELECT * FROM subcategorias").fetchall()
    conn.close()
    return render_template("categorias.html", categorias=categorias, subcategorias=subcategorias)


@app.route("/categorias/nueva", methods=["POST"])
def nueva_categoria():
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO categorias (tipo, nombre) VALUES (?, ?)", (tipo, nombre))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/categorias/editar/<int:cat_id>", methods=["POST"])
def editar_categoria(cat_id):
    nombre = request.form.get("nombre")
    tipo = request.form.get("tipo")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE categorias SET nombre=?, tipo=? WHERE id=?", (nombre, tipo, cat_id))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/categorias/eliminar/<int:cat_id>", methods=["POST"])
def eliminar_categoria(cat_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM categorias WHERE id=?", (cat_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/subcategorias/nueva", methods=["POST"])
def nueva_subcategoria():
    nombre = request.form.get("nombre")
    categoria_id = request.form.get("categoria_id")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO subcategorias (categoria_id, nombre) VALUES (?, ?)", (categoria_id, nombre))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/subcategorias/editar/<int:sub_id>", methods=["POST"])
def editar_subcategoria(sub_id):
    nombre = request.form.get("nombre")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE subcategorias SET nombre=? WHERE id=?", (nombre, sub_id))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/subcategorias/eliminar/<int:sub_id>", methods=["POST"])
def eliminar_subcategoria(sub_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM subcategorias WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))

@app.route("/logout")
def logout():
    session.clear()  # Limpia toda la sesión
    return redirect(url_for("login"))

# -------------------- LEYENDA --------------------
# Para modificar los anchos de columnas en la tabla Pedidos:
# - Edita en "pedidos.html" el bloque <style> con nth-child()
#   Ejemplo: #tablaPedidos th:nth-child(2) { width: 120px !important; }
# - O modifica en los "columnDefs" dentro del bloque DataTables en pedidos.html
#   Ejemplo: { targets: 1, width: "120px" }  -> Columna # Pedido
# Consulta la tabla de índices incluida en la documentación previa.

if __name__ == "__main__":
    app.run(debug=True)
