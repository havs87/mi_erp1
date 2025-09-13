-- ==========================
-- SCHEMA DE MI_ERP
-- Fecha: 2025-09-12 (actualizado)
-- ==========================

PRAGMA foreign_keys = ON;

-- --------------------------
-- TABLA: usuarios
-- --------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    mod_pedidos INTEGER DEFAULT 0,
    mod_movimientos INTEGER DEFAULT 0,
    mod_admin INTEGER DEFAULT 0,
    mod_usuarios INTEGER DEFAULT 0
);

-- Usuario administrador inicial
INSERT OR IGNORE INTO usuarios 
(id, username, password, is_admin, mod_pedidos, mod_movimientos, mod_admin, mod_usuarios)
VALUES 
(1, 'Administrador', '1812', 1, 1, 1, 1, 1);

-- --------------------------
-- TABLA: pedidos
-- --------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etapa TEXT DEFAULT 'P. Generado',
    numero_pedido TEXT NOT NULL,
    fecha TEXT NOT NULL,
    fecha_entrega_propuesta TEXT,
    fecha_entrega_real TEXT,
    motivo_retraso TEXT,
    canal TEXT,
    oc TEXT,
    doc_venta TEXT,
    cliente TEXT NOT NULL,
    descripcion TEXT,
    importe REAL DEFAULT 0,
    gasto REAL DEFAULT 0,
    moneda TEXT DEFAULT 'PEN'
);

-- --------------------------
-- TABLA: ingresos
-- --------------------------
CREATE TABLE IF NOT EXISTS ingresos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    monto REAL NOT NULL,
    forma_pago TEXT,
    fecha TEXT NOT NULL,
    depositado INTEGER DEFAULT 0,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
);

-- --------------------------
-- TABLA: categorias
-- --------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL, -- 'ingreso' o 'egreso'
    nombre TEXT NOT NULL
);

-- --------------------------
-- TABLA: subcategorias
-- --------------------------
CREATE TABLE IF NOT EXISTS subcategorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE CASCADE
);

-- --------------------------
-- TABLA: movimientos
-- --------------------------
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL, -- ingreso / egreso
    categoria_id INTEGER,
    subcategoria_id INTEGER,
    descripcion TEXT,
    monto REAL NOT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    FOREIGN KEY (subcategoria_id) REFERENCES subcategorias(id)
);

-- --------------------------
-- SEMILLA INICIAL
-- --------------------------

-- Categorías básicas
INSERT OR IGNORE INTO categorias (id, tipo, nombre) VALUES
(1, 'ingreso', 'Ventas'),
(2, 'ingreso', 'Servicios'),
(3, 'egreso', 'Transporte'),
(4, 'egreso', 'Insumos');

-- Subcategorías básicas
INSERT OR IGNORE INTO subcategorias (id, categoria_id, nombre) VALUES
(1, 1, 'Venta en tienda'),
(2, 1, 'Venta online'),
(3, 3, 'Gasolina'),
(4, 3, 'Mantenimiento');
