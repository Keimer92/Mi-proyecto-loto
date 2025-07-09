import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import sqlite3
import random
from datetime import datetime, timedelta
import hashlib
import os
import sys
import subprocess
import atexit
import re # Necesario para el procesamiento del reporte en PDF
import json 

from tkcalendar import DateEntry
from fpdf import FPDF, enums # Importar enums aquí
# print(f"FPDF module path: {FPDF.__module__}")
# print(f"FPDF version: {FPDF_VERSION if 'FPDF_VERSION' in globals() else 'Not found'}")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from collections import Counter
from datetime import datetime

# --- Configuración de la Base de Datos ---
DB_DIR = 'data'
DB_NAME = os.path.join(DB_DIR, 'loteria.db')
temp_pdf_files = [] # Lista para almacenar rutas de PDFs temporales para limpieza

def crear_tabla():
    """Crea las tablas 'ventas', 'configuracion', 'resultados_sorteo' y 'ui_configuracion' en la base de datos si no existen."""
    os.makedirs(DB_DIR, exist_ok=True)

    # ¡ESTAS DOS LÍNEAS SON FUNDAMENTALES Y DEBEN ESTAR AQUÍ AL INICIO DE LA FUNCIÓN!
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabla de Ventas (modificada para permitir múltiples ventas del mismo número)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_loteria TEXT NOT NULL,
            apuesta INTEGER NOT NULL,
            premio_potencial REAL NOT NULL,
            fecha_hora TEXT NOT NULL,
            sorteo_hora TEXT NOT NULL,
            venta_fecha_solo_dia TEXT NOT NULL
        )
    ''')

    # Tabla de Resultados del Sorteo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resultados_sorteo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_sorteo TEXT NOT NULL,
            hora_sorteo TEXT NOT NULL,
            numero_ganador TEXT NOT NULL,
            UNIQUE(fecha_sorteo, hora_sorteo)
        )
    ''')

    # --- INICIO DE CAMBIO CRÍTICO: Nueva estructura para la tabla 'configuracion' ---
    # Esta tabla es para configuraciones globales de la aplicación, con un ID fijo.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            id INTEGER PRIMARY KEY DEFAULT 1,
            clave_acceso TEXT,
            premio_por_cordoba_1 REAL DEFAULT 70.0,
            sorteo_activo TEXT DEFAULT 'DIA',
            hora_cierre_dia TEXT DEFAULT '13:00',
            hora_cierre_noche TEXT DEFAULT '21:00',
            monto_minimo_venta REAL DEFAULT 1.0,
            max_ventas_numero_sorteo INTEGER DEFAULT 100,
            tema TEXT DEFAULT 'clam'
        )
    ''')

    # Asegurarse de que siempre haya una fila en configuracion con id=1 para los ajustes
    cursor.execute("INSERT OR IGNORE INTO configuracion (id) VALUES (1)")

    # --- NUEVA TABLA: ui_configuracion para configuraciones específicas de la UI (como anchos de columnas) ---
    # Esta tabla usa el modelo clave/valor_json para settings dinámicos de UI.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ui_configuracion (
            clave TEXT PRIMARY KEY,
            valor_json TEXT
        )
    ''')

    # --- LÓGICA DE MIGRACIÓN PARA TABLA 'configuracion' ---
    # La lógica de migración que te di antes era para tu archivo "02.py".
    # Ahora que tienes "loto_actualizado.py" y la estructura de "configuracion" ha cambiado,
    # es mejor un enfoque de "si no existe un valor en la nueva columna, usa el por defecto o migra si es posible".

    # Migrar 'clave_acceso'
    cursor.execute("SELECT clave_acceso FROM configuracion WHERE id = 1")
    current_clave_acceso = cursor.fetchone()
    if not current_clave_acceso or not current_clave_acceso[0]:
        # Intentar migrar desde la vieja tabla de configuración si existiera
        try:
            temp_conn = sqlite3.connect(DB_NAME)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute("SELECT valor FROM configuracion WHERE clave = 'clave_acceso'")
            old_key_value = temp_cursor.fetchone()
            if old_key_value:
                new_key_value = old_key_value[0]
                cursor.execute("UPDATE configuracion SET clave_acceso = ? WHERE id = 1", (new_key_value,))
                print("✅ Clave de acceso migrada.")
            temp_conn.close()
        except sqlite3.OperationalError: # Tabla vieja no existe
            pass
        
        # Si después de la migración sigue sin clave o es nueva DB, inicializar
        cursor.execute("SELECT clave_acceso FROM configuracion WHERE id = 1")
        final_clave = cursor.fetchone()
        if not final_clave or not final_clave[0]:
            # No inicializar con el hash de una cadena vacía, sino dejarla como NULL para que el login se omita.
            # La clave se establecerá solo cuando el usuario la defina explícitamente en Configuración.
            clave_inicial_hash = None
            cursor.execute("UPDATE configuracion SET clave_acceso = ? WHERE id = 1", (clave_inicial_hash,))
            print("✅ Clave de acceso inicializada.")

    # Migrar 'premio_por_cordoba'
    cursor.execute("SELECT premio_por_cordoba_1 FROM configuracion WHERE id = 1")
    current_premio = cursor.fetchone()
    if not current_premio or current_premio[0] == 80.0: # Si es el valor por defecto, intentar migrar
        try:
            temp_conn = sqlite3.connect(DB_NAME)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute("SELECT valor FROM configuracion WHERE clave = 'premio_por_cordoba'")
            old_premio_value = temp_cursor.fetchone()
            if old_premio_value:
                try:
                    new_premio_value = float(old_premio_value[0])
                    cursor.execute("UPDATE configuracion SET premio_por_cordoba_1 = ? WHERE id = 1", (new_premio_value,))
                    print("✅ Premio por cordoba migrado.")
                except ValueError:
                    print("❌ No se pudo convertir el valor de 'premio_por_cordoba' a número. Usando valor por defecto.")
            temp_conn.close()
        except sqlite3.OperationalError: # Tabla vieja no existe
            pass
    
    # Asegurarse de que el tema tenga un valor
    cursor.execute("SELECT tema FROM configuracion WHERE id = 1")
    current_tema = cursor.fetchone()
    if not current_tema or not current_tema[0]:
        # Intentar migrar desde la vieja tabla de configuración si existiera
        try:
            temp_conn = sqlite3.connect(DB_NAME)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute("SELECT valor FROM configuracion WHERE clave = 'tema'")
            old_tema_value = temp_cursor.fetchone()
            if old_tema_value:
                new_tema_value = old_tema_value[0]
                cursor.execute("UPDATE configuracion SET tema = ? WHERE id = 1", (new_tema_value,))
                print("✅ Tema migrado.")
            temp_conn.close()
        except sqlite3.OperationalError:
            pass

        cursor.execute("SELECT tema FROM configuracion WHERE id = 1")
        final_tema = cursor.fetchone()
        if not final_tema or not final_tema[0]:
            cursor.execute("UPDATE configuracion SET tema = 'clam' WHERE id = 1")
            print("✅ Tema inicializado.")

    # --- FIN DE CAMBIO CRÍTICO ---

    # ¡ESTAS DOS LÍNEAS DEBEN ESTAR AL FINAL DE LA FUNCIÓN, DESPUÉS DE TODAS LAS CREACIONES DE TABLAS Y MIGRACIONES!
    conn.commit()
    conn.close()

# --- Funciones de Lógica de Negocio ---

def obtener_premio_por_cordoba_db():
    """Obtiene el valor del premio por cada 1 córdoba de la base de datos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT premio_por_cordoba_1 FROM configuracion WHERE id = 1")
    resultado = cursor.fetchone()
    conn.close()
    try:
        return int(resultado[0]) if resultado else 70
    except ValueError:
        return 70 # En caso de que el valor almacenado no sea un número válido
    

# --- Nuevas Funciones Auxiliares para Resumen Diario ---

def obtener_numero_mas_vendido_hoy():
    """Calcula y retorna el número más vendido del día actual y la cantidad de veces que se vendió."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT numero, COUNT(numero) as cantidad_ventas
        FROM ventas
        WHERE substr(fecha_venta, 1, 10) = ?
        GROUP BY numero
        ORDER BY cantidad_ventas DESC, numero ASC
        LIMIT 1
    """, (hoy_str,))
    resultado = cursor.fetchone()
    conn.close()

    if resultado:
        return f"{resultado[0]} (Vend. {resultado[1]} veces)"
    return "N/A"

def calcular_total_apostado_hoy():
    """Calcula y retorna la suma total de las apuestas realizadas el día actual."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT SUM(apuesta)
        FROM ventas
        WHERE substr(fecha_venta, 1, 10) = ?
    """, (hoy_str,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total is not None else 0.0

def calcular_ganancia_potencial_total_hoy():
    """Calcula y retorna la suma total de la ganancia potencial del día actual."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT SUM(premio_potencial)
        FROM ventas
        WHERE substr(fecha_venta, 1, 10) = ?
    """, (hoy_str,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total is not None else 0.0
    
def obtener_monto_minimo_venta_db():
    """Obtiene el monto mínimo de venta de la base de datos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT monto_minimo_venta FROM configuracion WHERE id = 1")
    resultado = cursor.fetchone()
    conn.close()
    return float(resultado[0]) if resultado else 1.0 # Por defecto 1.0 si no se encuentra

def guardar_configuracion_ui_db(clave, valor_json):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO ui_configuracion (clave, valor_json) VALUES (?, ?)", (clave, valor_json))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al guardar configuración UI '{clave}': {e}")
    finally:
        conn.close()

def cargar_configuracion_ui_db(clave):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT valor_json FROM ui_configuracion WHERE clave = ?", (clave,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except sqlite3.Error as e:
        print(f"Error al cargar configuración UI '{clave}': {e}")
        return None
    finally:
        conn.close()

def obtener_numero_mas_vendido_del_dia():
    """
    Obtiene el número de lotería más vendido del día actual.
    Retorna el número como una cadena (ej. "05") y su conteo,
    o None, 0 si no hay ventas hoy.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute(f"""
        SELECT numero_loteria, COUNT(numero_loteria) as ventas_count
        FROM ventas
        WHERE venta_fecha_solo_dia = ?
        GROUP BY numero_loteria
        ORDER BY ventas_count DESC, numero_loteria ASC
        LIMIT 1
    """, (hoy,))
    
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado:
        return resultado[0], resultado[1] # Retorna (numero_loteria, ventas_count)
    else:
        return None, 0 # No hay ventas para hoy

def obtener_tema_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT tema FROM configuracion WHERE id = 1")
    tema = cursor.fetchone()
    conn.close()
    return tema[0] if tema else 'clam' # Retorna el tema o 'clam' por defecto

def actualizar_tema_db(nuevo_tema):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE configuracion SET tema = ? WHERE id = 1", (nuevo_tema,))
    conn.commit()
    conn.close()

def calcular_premio(apuesta):
    """Calcula el premio potencial basado en la apuesta y el valor configurado."""
    premio_por_cordoba = obtener_premio_por_cordoba_db()
    try:
        apuesta_int = int(apuesta)
        return apuesta_int * premio_por_cordoba if apuesta_int > 0 else 0
    except ValueError:
        return 0

def formatear_numero_loteria(numero):
    """Asegura que el número de lotería tenga siempre 2 dígitos (ej. 05 en vez de 5)."""
    try:
        numero_int = int(numero)
        return f"{numero_int:02d}"
    except ValueError:
        return ""

# --- Funciones de Interacción con la Base de Datos (Ventas) ---

def registrar_venta_db(numero, apuesta, premio, sorteo_hora):
    """
    Registra o actualiza una venta de lotería en la base de datos.
    Si ya existe una venta para el mismo número, fecha y sorteo, se actualiza la apuesta y el premio,
    y la 'fecha_hora' de la última modificación. De lo contrario, se inserta una nueva venta.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    fecha_actual_solo_dia = datetime.now().strftime('%Y-%m-%d')
    fecha_hora_completa_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    numero_formateado = formatear_numero_loteria(numero)

    try:
        # Intentar encontrar una venta existente para el mismo número, día y sorteo
        cursor.execute('''
            SELECT apuesta, premio_potencial FROM ventas
            WHERE numero_loteria = ? AND venta_fecha_solo_dia = ? AND sorteo_hora = ?
        ''', (numero_formateado, fecha_actual_solo_dia, sorteo_hora))
        
        venta_existente = cursor.fetchone()

        if venta_existente:
            apuesta_existente, premio_existente = venta_existente
            nueva_apuesta_total = apuesta_existente + apuesta
            # El nuevo premio potencial se calcula de nuevo, no se suma, para evitar errores si el multiplicador de premio cambia
            nuevo_premio_total = calcular_premio(nueva_apuesta_total)
            
            cursor.execute('''
                UPDATE ventas
                SET apuesta = ?, premio_potencial = ?, fecha_hora = ?
                WHERE numero_loteria = ? AND venta_fecha_solo_dia = ? AND sorteo_hora = ?
            ''', (nueva_apuesta_total, nuevo_premio_total, fecha_hora_completa_actual,
                  numero_formateado, fecha_actual_solo_dia, sorteo_hora))
            conn.commit()
            return True, f"✅ Venta actualizada: Número {numero_formateado} ({sorteo_hora}), Apuesta Total C${nueva_apuesta_total}, Premio Total C${nuevo_premio_total} (última mod: {fecha_hora_completa_actual})"
        else:
            # Insertar una nueva venta si no existe
            cursor.execute('''
                INSERT INTO ventas (numero_loteria, apuesta, premio_potencial, fecha_hora, sorteo_hora, venta_fecha_solo_dia)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (numero_formateado, apuesta, premio, fecha_hora_completa_actual, sorteo_hora, fecha_actual_solo_dia))
            conn.commit()
            return True, f"✅ Venta registrada: Número {numero_formateado} ({sorteo_hora}), Apuesta C${apuesta}, Premio C${premio}, Fecha: {fecha_hora_completa_actual}"

    except sqlite3.Error as e:
        return False, f"❌ Error al registrar/actualizar la venta: {e}"
    finally:
        conn.close()

def obtener_todas_las_ventas_db():
    """Obtiene todos los registros de ventas de la base de datos (individuales, sin agrupar)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, numero_loteria, apuesta, premio_potencial, fecha_hora, sorteo_hora, venta_fecha_solo_dia FROM ventas ORDER BY fecha_hora DESC")
    ventas = cursor.fetchall()
    conn.close()
    return ventas

def obtener_historial_ventas_numero_db(numero):
    """
    Obtiene el historial de ventas para un número de lotería específico.
    Retorna una lista de tuplas con los datos de venta.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    numero_formateado = formatear_numero_loteria(numero)
    cursor.execute('''
        SELECT fecha_hora, sorteo_hora, apuesta, premio_potencial
        FROM ventas
        WHERE numero_loteria = ?
        ORDER BY fecha_hora DESC
    ''', (numero_formateado,))
    historial = cursor.fetchall()
    conn.close()
    return historial

def eliminar_ultima_venta_db():
    """Elimina el último registro de venta de la base de datos (NO USADO EN ESTA LÓGICA AGRUPADA)."""
    # Esta función ahora es menos útil con la lógica de agrupación y actualización.
    # Si se elimina una venta, se debería decrementar la apuesta y premio del registro agrupado,
    # o eliminar el registro si la apuesta llega a cero.
    # Por ahora, la dejaré como está, pero ten en cuenta que no funcionará como esperas
    # si la usas con la lógica de "números agrupados".
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Aquí deberías pensar si quieres eliminar la "última venta individual" o la "última apuesta"
        # Para la lógica actual de agrupación, esto es complicado.
        # Por simplicidad, esta función no se usará directamente con la nueva lógica de reporte agrupado.
        # Si se desea "deshacer" una venta, se debería implementar una lógica más compleja de ajuste del total.
        messagebox.showwarning("Advertencia", "La función 'Eliminar Última Venta' no es compatible con la nueva lógica de agrupación. Para deshacer una venta, necesitas ajustar la apuesta directamente.")
        return False, "Función deshabilitada debido a la lógica de agrupación."
    except sqlite3.Error as e:
        return False, f"❌ Error al eliminar la última venta: {e}"
    finally:
        conn.close()

# <<< CAMBIO INICIADO: Modificar la firma de la función para aceptar un rango de fechas.
def obtener_ventas_para_reporte_db(tipo_reporte=None, fecha_inicio=None, fecha_fin=None, mes_numero_seleccionado=None, anio_seleccionado=None, sorteo_seleccionado=None):
# <<< CAMBIO FINALIZADO
    """
    Obtiene las ventas para un período específico (diario, semanal, mensual) o por fecha/sorteo.
    Agrupa por numero_loteria, venta_fecha_solo_dia y sorteo para mostrar la suma total.
    Ordena por la última fecha_hora de modificación de cada grupo.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    ahora = datetime.now()
    
    where_clauses = []
    params = []

    if tipo_reporte:
        if tipo_reporte == 'diario':
            fecha_comienzo = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
            where_clauses.append("fecha_hora >= ?")
            params.append(fecha_comienzo.strftime('%Y-%m-%d %H:%M:%S'))
        elif tipo_reporte == 'semanal':
            dias_restar = ahora.weekday() # 0 para lunes, 6 para domingo
            fecha_comienzo = ahora - timedelta(days=dias_restar)
            fecha_comienzo = fecha_comienzo.replace(hour=0, minute=0, second=0, microsecond=0)
            where_clauses.append("fecha_hora >= ?")
            params.append(fecha_comienzo.strftime('%Y-%m-%d %H:%M:%S'))
        elif tipo_reporte == 'mensual':
            if mes_numero_seleccionado and anio_seleccionado:
                try:
                    mes_int = int(mes_numero_seleccionado)
                    anio_int = int(anio_seleccionado)
                    if mes_int == 12:
                        fecha_fin_mes = datetime(anio_int + 1, 1, 1) - timedelta(days=1)
                    else:
                        fecha_fin_mes = datetime(anio_int, mes_int + 1, 1) - timedelta(days=1)
                    
                    fecha_inicio_mes = datetime(anio_int, mes_int, 1)

                    where_clauses.append("fecha_hora BETWEEN ? AND ?")
                    params.append(fecha_inicio_mes.strftime('%Y-%m-%d 00:00:00'))
                    params.append(fecha_fin_mes.strftime('%Y-%m-%d 23:59:59'))
                except ValueError:
                    pass
        # <<< CAMBIO INICIADO: Usar BETWEEN para el rango de fechas.
        elif tipo_reporte == 'por_fecha':
            if fecha_inicio and fecha_fin:
                where_clauses.append("venta_fecha_solo_dia BETWEEN ? AND ?")
                params.append(fecha_inicio)
                params.append(fecha_fin)
        # <<< CAMBIO FINALIZADO
    
    if sorteo_seleccionado and sorteo_seleccionado != "Todos":
        where_clauses.append("sorteo_hora = ?")
        params.append(sorteo_seleccionado)

    query = '''
        SELECT 
            numero_loteria, 
            SUM(apuesta) AS total_apuesta, 
            SUM(premio_potencial) AS total_premio, 
            venta_fecha_solo_dia, 
            sorteo_hora,
            MAX(fecha_hora) AS ultima_modificacion_hora_venta -- Obtener la última fecha_hora de venta
        FROM ventas
    '''
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += '''
        GROUP BY numero_loteria, venta_fecha_solo_dia, sorteo_hora
        ORDER BY ultima_modificacion_hora_venta DESC, numero_loteria ASC -- Ordenar por la última modificación
    '''
    # print(f"DEBUG: SQL Query (ventas agrupadas, ordenado por ultima_modificacion_hora_venta): {query}")
    # print(f"DEBUG: SQL Params (ventas agrupadas): {params}")

    cursor.execute(query, tuple(params))
    ventas = cursor.fetchall()
    # print(f"DEBUG: Resultados de la consulta (ventas agrupadas): {ventas}")
    conn.close()
    return ventas

# --- Funciones de Interacción con la Base de Datos (Resultados de Sorteo) ---

def registrar_numero_ganador_db(fecha, sorteo, numero_ganador):
    """
    Registra el número ganador para una fecha y sorteo específicos.
    Si ya existe, lo actualiza.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    numero_formateado = formatear_numero_loteria(numero_ganador)

    try:
        cursor.execute('''
            SELECT id FROM resultados_sorteo
            WHERE fecha_sorteo = ? AND hora_sorteo = ?
        ''', (fecha, sorteo))
        
        registro_existente = cursor.fetchone()

        if registro_existente:
            cursor.execute('''
                UPDATE resultados_sorteo
                SET numero_ganador = ?
                WHERE fecha_sorteo = ? AND hora_sorteo = ?
            ''', (numero_formateado, fecha, sorteo))
            conn.commit()
            return True, f"✅ Número ganador para {fecha} - {sorteo} actualizado a {numero_formateado}."
        else:
            cursor.execute('''
                INSERT INTO resultados_sorteo (fecha_sorteo, hora_sorteo, numero_ganador)
                VALUES (?, ?, ?)
            ''', (fecha, sorteo, numero_formateado))
            conn.commit()
            return True, f"✅ Número ganador {numero_formateado} registrado para {fecha} - {sorteo}."
    except sqlite3.Error as e:
        return False, f"❌ Error al registrar/actualizar número ganador: {e}"
    finally:
        conn.close()

def consultar_numero_ganador_db(fecha, sorteo):
    """Consulta el número ganador para una fecha y sorteo específicos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT numero_ganador
            FROM resultados_sorteo
            WHERE fecha_sorteo = ? AND hora_sorteo = ?
        ''', (fecha, sorteo))
        resultado = cursor.fetchone()
        conn.close()
        return resultado[0] if resultado else None
    except sqlite3.Error as e:
        print(f"Error al consultar número ganador: {e}")
        return None
    finally:
        conn.close()

def obtener_ultimos_ganadores_db(limite=5):
    """Obtiene los últimos números ganadores registrados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT fecha_sorteo, hora_sorteo, numero_ganador
            FROM resultados_sorteo
            ORDER BY fecha_sorteo DESC, hora_sorteo DESC
            LIMIT ?
        ''', (limite,))
        ganadores = cursor.fetchall()
        return ganadores
    except sqlite3.Error as e:
        print(f"Error al obtener últimos ganadores: {e}")
        return []
    finally:
        conn.close()

# <<< CAMBIO INICIADO: Modificar la firma de la función para aceptar un rango de fechas.
def obtener_ganadores_para_reporte_db(tipo_reporte=None, fecha_inicio=None, fecha_fin=None, mes_numero_seleccionado=None, anio_seleccionado=None, sorteo_seleccionado=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    ahora = datetime.now()
    
    where_clauses = []
    params = []

    if tipo_reporte:
        if tipo_reporte == 'diario':
            fecha_comienzo = ahora.strftime('%Y-%m-%d')
            where_clauses.append("r.fecha_sorteo >= ?")
            params.append(fecha_comienzo)
        elif tipo_reporte == 'semanal':
            lunes = (ahora - timedelta(days=ahora.weekday())).strftime('%Y-%m-%d')
            where_clauses.append("r.fecha_sorteo >= ?")
            params.append(lunes)
        elif tipo_reporte == 'mensual':
            if mes_numero_seleccionado and anio_seleccionado:
                fecha_inicio = f"{anio_seleccionado}-{mes_numero_seleccionado}-01"
                if mes_numero_seleccionado == "12":
                    fecha_fin = f"{int(anio_seleccionado)+1}-01-01"
                else:
                    fecha_fin = f"{anio_seleccionado}-{int(mes_numero_seleccionado)+1:02d}-01"
                where_clauses.append("r.fecha_sorteo BETWEEN ? AND ?")
                params.extend([fecha_inicio, fecha_fin])
        elif tipo_reporte == 'por_fecha':
            if fecha_inicio and fecha_fin:
                where_clauses.append("r.fecha_sorteo BETWEEN ? AND ?")
                params.extend([fecha_inicio, fecha_fin])

    if sorteo_seleccionado and sorteo_seleccionado != "Todos":
        where_clauses.append("r.hora_sorteo = ?")
        params.append(sorteo_seleccionado)

    query = '''
        SELECT 
            r.fecha_sorteo,
            r.hora_sorteo,
            r.numero_ganador,
            IFNULL(SUM(v.apuesta), 0) AS total_apostado,
            IFNULL(SUM(v.premio_potencial), 0) AS premio_pagado
        FROM resultados_sorteo r
        LEFT JOIN ventas v
            ON v.venta_fecha_solo_dia = r.fecha_sorteo
            AND v.sorteo_hora = r.hora_sorteo
            AND v.numero_loteria = r.numero_ganador
    '''

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += '''
        GROUP BY r.fecha_sorteo, r.hora_sorteo, r.numero_ganador
        ORDER BY r.fecha_sorteo DESC, r.hora_sorteo ASC
    '''

    cursor.execute(query, tuple(params))
    resultados = cursor.fetchall()
    conn.close()
    return resultados

# --- Funciones de Acceso y Configuración ---

def verificar_clave_db(clave_ingresada):
    """Verifica si la clave ingresada coincide con la almacenada en la DB."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT clave_acceso FROM configuracion WHERE id = 1")
    clave_hash_almacenada = cursor.fetchone()
    conn.close()

    if clave_hash_almacenada:
        return hashlib.sha256(clave_ingresada.encode()).hexdigest() == clave_hash_almacenada[0]
    return False

def actualizar_clave_db(nueva_clave):
    """Actualiza la clave de acceso en la base de datos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    nueva_clave_hash = hashlib.sha256(nueva_clave.encode()).hexdigest()
    try:
        cursor.execute("UPDATE configuracion SET clave_acceso = ? WHERE id = 1", (nueva_clave_hash,))
        return True, "✅ Clave de acceso actualizada correctamente."
    except sqlite3.Error as e:
        return False, f"❌ Error al actualizar la clave: {e}"
    finally:
        conn.close()

def actualizar_premio_por_cordoba_db(nuevo_valor):
    """Actualiza el valor del premio por cada C$1 en la base de datos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE configuracion SET premio_por_cordoba_1 = ? WHERE id = 1", (nuevo_valor,))
        conn.commit()
        return True, "✅ Premio por cada C$1 actualizado correctamente."
    except sqlite3.Error as e:
        return False, f"❌ Error al actualizar el premio por C$1: {e}"
    finally:
        conn.close()

def existe_clave_acceso_configurada():
    """
    Verifica si existe una clave de acceso configurada en la base de datos
    que NO sea el hash de una cadena vacía.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT clave_acceso FROM configuracion WHERE id = 1")
    clave_hash_almacenada = cursor.fetchone()
    conn.close()

    # Calcular el hash de una cadena vacía para compararlo
    hash_clave_vacia = hashlib.sha256("".encode()).hexdigest()

    # Retorna True solo si hay una clave almacenada Y es diferente al hash de una cadena vacía
    # Si clave_hash_almacenada es None (porque el campo es NULL), el primer 'if' es falso y retorna False.
    if clave_hash_almacenada and clave_hash_almacenada[0] != hash_clave_vacia:
        return True
    return False


# --- Funciones de utilidad para centrar ventanas ---
def center_window(window):
    """Centra una ventana Toplevel o Tk en la pantalla."""
    window.update_idletasks() # Asegura que el tamaño de la ventana sea calculado
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')

# --- Funciones para la eliminación de PDFs temporales al salir ---
def cleanup_temp_pdfs():
    """Elimina los archivos PDF temporales generados."""
    for pdf_path in temp_pdf_files:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                # print(f"Eliminado PDF temporal: {pdf_path}")
        except Exception as e:
            print(f"Error al eliminar PDF temporal {pdf_path}: {e}")

# Registrar la función de limpieza para que se ejecute al salir del programa
atexit.register(cleanup_temp_pdfs)

# --- Clase de la Ventana de Login ---
class LoginWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Acceso al Sistema")
        # self.geometry("300x150") # ELIMINAR/COMENTAR ESTA LÍNEA PARA QUE CENTER_WINDOW FUNCIONE
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.login_successful = False

        self.create_widgets()
        
        # Centrar la ventana después de crear los widgets para que el tamaño sea conocido
        self.update_idletasks() # Asegura que el tamaño se calcule antes de centrar
        center_window(self) # Llama a la nueva función para centrarla

        self.clave_entry.focus_set()

    def create_widgets(self):
        self.clave_var = tk.StringVar()

        # Usar un padding más generoso y quizás un color de fondo para el frame
        main_frame = ttk.Frame(self, padding="20 20 20 20")
        main_frame.pack(expand=True) # expand=True para que el frame se centre dentro de la ventana

        ttk.Label(main_frame, text="Clave de Acceso:", font=("Arial", 11, "bold")).grid(row=0, column=0, pady=5, sticky="w")
        self.clave_entry = ttk.Entry(main_frame, show="*", textvariable=self.clave_var, font=("Arial", 11))
        self.clave_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        # Enlazar la tecla Enter a la función check_login
        self.clave_entry.bind("<Return>", lambda event=None: self.check_login())


        # Botón con un estilo un poco más prominente
        ttk.Button(main_frame, text="Ingresar", command=self.check_login, style='Accent.TButton').grid(row=1, column=0, columnspan=2, pady=15)

        main_frame.grid_columnconfigure(1, weight=1) # Permite que el campo de entrada se expanda


    def check_login(self):
        clave_ingresada = self.clave_var.get()
        if verificar_clave_db(clave_ingresada):
            self.login_successful = True
            self.destroy()
        else:
            messagebox.showerror("Error de Acceso", "Clave incorrecta. Intente de nuevo.")
            self.clave_var.set("")
            self.clave_entry.focus_set()

    def on_closing(self):
        if messagebox.askokcancel("Salir", "¿Estás seguro de que quieres salir?"):
            self.master.destroy()
            sys.exit(0)

# --- Clase Principal de la Aplicación GUI con Pestañas ---

class AppLoteria:
    def __init__(self, root):
        self.root = root
        root.title("Sistema de Venta de Lotería")
        root.state('zoomed') # Maximiza la ventana al iniciar
        root.resizable(True, True) # Permitir redimensionar después de maximizar (opcional)
        
        
        # --- Estilo y Temas ---
        self.style = ttk.Style(root)
        #self.root.tk.call("source", "azure.tcl")
        self.style.theme_use(obtener_tema_db())  # Ya lo estás usando

        # Personalizar colores y fuentes para un toque más moderno
        self.style.configure('.', font=("Arial", 10)) # Fuente por defecto para todo
        self.style.configure('TLabel', font=("Arial", 10))
        self.style.configure('TButton', font=("Arial", 10, "bold"), padding=6) # Más padding para botones
        self.style.map('TButton',
                       background=[('active', '#e0e0e0'), ('!disabled', '#f0f0f0')], # Colores al pasar el mouse
                       foreground=[('active', 'black'), ('!disabled', 'black')]) # Texto en botones

        # Estilo para un botón "accent" (como el de Ingresar)
        self.style.configure('Accent.TButton', background='#4CAF50', foreground='white', font=("Arial", 11, "bold"))
        self.style.map('Accent.TButton',
                       background=[('active', '#45a049'), ('!disabled', '#4CAF50')])

        self.style.configure('Danger.TButton', background='#e53935', foreground='white', font=("Arial", 11, "bold"))
        self.style.map('Danger.TButton',
                    background=[('active', '#c62828'), ('!disabled', '#e53935')],
                    foreground=[('!disabled', 'white')])


        self.style.configure('TEntry', font=("Arial", 11))
        self.style.configure('TRadiobutton', font=("Arial", 10))
        self.style.configure('TNotebook.Tab', font=("Arial", 12, "bold")) # Pestañas más grandes y negritas
        self.style.configure('Treeview.Heading', font=("Arial", 11, "bold"), background='#d0d0d0') # Encabezados de tabla
        self.style.configure('Treeview', font=("Arial", 10), rowheight=22) # Filas de tabla con más altura
        self.style.map('Treeview', background=[('selected', '#a0c0e0')]) # Resaltado de selección

        # Tags para Treeview de ganadores
        self.style.configure('Treeview', rowheight=25) # Un poco más de altura para las filas
        self.tree_ganadores_ventas_tags = ('no_ingresado',)
        self.style.configure('no_ingresado', background='red', foreground='white')


        # Opciones de sorteos globales
        self.sorteo_options_all = ('11 AM', '03 PM', '06 PM', '09 PM')

        # Variables para la pestaña de ventas
        self.numero_var = tk.StringVar()
        self.apuesta_var = tk.StringVar()
        self.premio_calculado_var = tk.StringVar(value="C$0")
        self.sorteo_var = tk.StringVar()
        self.apuesta_var.trace_add("write", self.actualizar_premio_calculado)
        self.sorteo_var.trace_add("write", self.update_top_info)

        # --- Parte Superior: Fecha y Sorteo Actual ---
        self.top_info_frame = ttk.Frame(self.root, relief="ridge", borderwidth=2)
        self.top_info_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.current_date_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%Y'))
        self.current_sorteo_var = tk.StringVar()

        ttk.Label(self.top_info_frame, textvariable=self.current_date_var, font=("Arial", 18, "bold"), foreground="blue").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Label(self.top_info_frame, textvariable=self.current_sorteo_var, font=("Arial", 18, "bold"), foreground="darkgreen").pack(side=tk.RIGHT, padx=10, pady=5)
        
        self._set_initial_sorteo_selection_venta()
        self.update_top_info()


        # Crear el widget Notebook (pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, pady=(5, 10), fill="both", expand=True)

        # Crear frames para cada pestaña
        self.tab_ventas = ttk.Frame(self.notebook)
        self.tab_sorteos = ttk.Frame(self.notebook)
        self.tab_reportes = ttk.Frame(self.notebook)
        self.tab_configuracion = ttk.Frame(self.notebook) # Nueva pestaña
        
        

        self.notebook.add(self.tab_ventas, text="Ventas")
        self.notebook.add(self.tab_sorteos, text="Gestión de Sorteos")
        self.notebook.add(self.tab_reportes, text="Reportes")

        self.tab_graficos = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_graficos, text="Gráficos")  # ← antes de Configuración
        self.crear_widgets_tab_graficos()  # Asegurate de mantenerlo también aquí

        self.tab_configuracion = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_configuracion, text="Configuración")

        
        
        # Inicializar widgets para cada pestaña
        self.crear_widgets_tab_ventas()
        self.actualizar_estado_ganadores_ventas()
        self.crear_widgets_tab_sorteos()
        self.crear_widgets_tab_reportes()
        self.crear_widgets_tab_configuracion() # Llamar a la nueva función

        # Enlazar evento de cambio de pestaña para actualizar listas/datos cuando se selecciona una pestaña
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # Variables para almacenar los datos del reporte en bruto para PDF
        self.report_data = [] # Esto almacenará la lista de tuplas (numero, apuesta_total, premio_total, fecha, sorteo)
        self.report_type_data = "Ventas" # Para saber si el reporte actual es de Ventas o Ganadores


    def eliminar_ultima_venta_gui(self):
        confirmado = messagebox.askyesno("Confirmar", "¿Estás seguro de que deseas eliminar la última venta registrada?")
        if confirmado:
            exito, mensaje = eliminar_ultima_venta_valida_db()
            self.lbl_estado.config(text=mensaje)
            self.actualizar_estado_ganadores_ventas()  # Si quieres refrescar también los datos


    def actualizar_resumen_ventas_dia(self):
        """
        Actualiza el Treeview con el resumen de ventas agrupadas por número y sorteo del día actual.
        """
        # Limpiar el Treeview existente para recargar los datos
        for item in self.tree_historial_resumen.get_children():
            self.tree_historial_resumen.delete(item)

        hoy_str = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Consulta para obtener las ventas del día, agrupadas por número_loteria y sorteo_hora
        cursor.execute('''
            SELECT 
                numero_loteria, 
                SUM(apuesta) AS total_apuesta, 
                SUM(premio_potencial) AS total_premio, 
                sorteo_hora
            FROM ventas
            WHERE venta_fecha_solo_dia = ?
            GROUP BY numero_loteria, sorteo_hora
            ORDER BY total_premio DESC, sorteo_hora ASC
        ''', (hoy_str,))

        ventas_agrupadas = cursor.fetchall()
        conn.close()

        # Si no hay ventas para hoy, mostrar un mensaje
        if not ventas_agrupadas:
            self.tree_historial_resumen.insert("", "end", values=("", "No hay ventas registradas para hoy", "", ""))
            return

        # Insertar los datos obtenidos en el Treeview
        for venta in ventas_agrupadas:
            numero, total_apuesta, total_premio, sorteo_hora = venta
            self.tree_historial_resumen.insert("", "end", values=(
                numero,
                f"C${total_apuesta:,.2f}",
                f"C${total_premio:,.2f}",
                sorteo_hora
            ))

    def mostrar_controles_periodo_busqueda(self):
        for widget in self.frame_controles_fecha.winfo_children():
            widget.grid_remove()

        periodo = self.periodo_busqueda_var.get()
        if periodo == "mensual":
            ttk.Label(self.frame_controles_fecha, text="Mes:").grid(row=0, column=0, padx=2)
            self.combo_mes_busqueda.grid(row=0, column=1, padx=2)
            ttk.Label(self.frame_controles_fecha, text="Año:").grid(row=0, column=2, padx=2)
            self.combo_anio_busqueda.grid(row=0, column=3, padx=2)
        elif periodo == "rango":
            ttk.Label(self.frame_controles_fecha, text="Desde:").grid(row=0, column=0, padx=2)
            self.fecha_inicio_entry.grid(row=0, column=1, padx=2)
            ttk.Label(self.frame_controles_fecha, text="Hasta:").grid(row=0, column=2, padx=2)
            self.fecha_fin_entry.grid(row=0, column=3, padx=2)


    def crear_widgets_tab_ventas(self):
        # --- Crear el PanedWindow principal para las tres columnas ---
        self.ventas_paned_window = ttk.PanedWindow(self.tab_ventas, orient=tk.HORIZONTAL)
        
        # Lo colocamos en la fila 0 y que abarque todas las columnas para que sea el contenedor principal
        self.ventas_paned_window.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        # Configurar la fila y columna del tab_ventas donde se ubicará el PanedWindow
        self.tab_ventas.grid_rowconfigure(0, weight=1)
        self.tab_ventas.grid_columnconfigure(0, weight=1) # El PanedWindow es el único en col 0, que se expande

        # --- Panel de venta de número (self.frame_venta) ---
        self.frame_venta = ttk.LabelFrame(self.ventas_paned_window, text="Vender Número")
        self.ventas_paned_window.add(self.frame_venta, weight=1) # Añadir al PanedWindow
        self.frame_venta.columnconfigure(1, weight=1) # Mantener configuración interna

        ttk.Label(self.frame_venta, text="Número (00-99):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.numero_entry = ttk.Entry(self.frame_venta, width=6, textvariable=self.numero_var, font=("Arial", 11, "bold"))
        self.numero_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.numero_entry.bind("<Return>", lambda event: self.apuesta_entry.focus_set())

        ttk.Label(self.frame_venta, text="Apuesta (desde C$1):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.apuesta_entry = ttk.Entry(self.frame_venta, width=6, textvariable=self.apuesta_var, font=("Arial", 11, "bold"))
        self.apuesta_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.apuesta_entry.bind("<Return>", lambda event: self.btn_vender.invoke())

        ttk.Label(self.frame_venta, text="Premio Potencial:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.lbl_premio_calculado = ttk.Label(self.frame_venta, textvariable=self.premio_calculado_var, font=("Arial", 11, "bold"), foreground="green")
        self.lbl_premio_calculado.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        self.sorteo_radio_frame_venta = ttk.LabelFrame(self.frame_venta, text="Sorteo")
        self.sorteo_radio_frame_venta.grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        for i, sorteo in enumerate(self.sorteo_options_all):
            rb = ttk.Radiobutton(self.sorteo_radio_frame_venta, text=sorteo, variable=self.sorteo_var, value=sorteo)
            rb.grid(row=0, column=i, padx=5, pady=2)
        for i in range(4):
            self.sorteo_radio_frame_venta.grid_columnconfigure(i, weight=1)

        self.btn_vender = ttk.Button(self.frame_venta, text="Vender Número", command=self.vender_numero_gui, style='Accent.TButton')
        self.btn_vender.grid(row=4, column=0, columnspan=2, pady=10)

        self.btn_eliminar_venta = ttk.Button(self.frame_venta, text="Eliminar Última Venta", command=self.eliminar_ultima_venta_gui, style='Danger.TButton')
        self.btn_eliminar_venta.grid(row=5, column=0, columnspan=2, pady=5)


        # --- Panel de Resumen de Ventas del Día (nueva implementación) ---
        historial_frame = ttk.LabelFrame(self.ventas_paned_window, text="Resumen de Ventas del Día")
        self.ventas_paned_window.add(historial_frame, weight=1) # Añadir al PanedWindow

        
        # Configuración interna del historial_frame para el Treeview
        historial_frame.rowconfigure(0, weight=1) # La fila del treeview que se expandirá
        historial_frame.columnconfigure(0, weight=1) # La columna del treeview que se expandirá

        # Nuevo Treeview para el resumen diario
        self.tree_historial_resumen = ttk.Treeview(historial_frame, columns=("Numero", "Apuesta Total", "Premio Potencial", "Sorteo"), show="headings")
        self.tree_historial_resumen.grid(row=0, column=0, padx=5, pady=5, sticky="nsew") # Ahora ocupa row=0, column=0

        # Definir encabezados de las columnas para el resumen diario
        self.tree_historial_resumen.heading("Numero", text="Número")
        self.tree_historial_resumen.heading("Apuesta Total", text="Apuesta Total")
        self.tree_historial_resumen.heading("Premio Potencial", text="Premio Potencial")
        self.tree_historial_resumen.heading("Sorteo", text="Sorteo")

        # Configurar el ancho y alineación de las columnas
        self.tree_historial_resumen.column("Numero", width=80, anchor="center")
        self.tree_historial_resumen.column("Apuesta Total", width=100, anchor="center")
        self.tree_historial_resumen.column("Premio Potencial", width=120, anchor="center")
        self.tree_historial_resumen.column("Sorteo", width=80, anchor="center")

        self.persistir_anchos_treeview(
            treeview_widget=self.tree_historial_resumen,
            clave_sqlite="ventas_resumen_columnas",
            columnas=["Numero", "Apuesta Total", "Premio Potencial", "Sorteo"]
        )


        # Añadir un scrollbar vertical al Treeview
        scrollbar_historial = ttk.Scrollbar(self.tree_historial_resumen, orient="vertical", command=self.tree_historial_resumen.yview)
        self.tree_historial_resumen.configure(yscrollcommand=scrollbar_historial.set)
        scrollbar_historial.pack(side="right", fill="y")

        # --- Ganadores del día (self.frame_ganadores_dia) ---
        self.frame_ganadores_dia = ttk.LabelFrame(self.ventas_paned_window, text="Ganadores del Día")
        self.ventas_paned_window.add(self.frame_ganadores_dia, weight=1) # Añadir al PanedWindow
        
        self.frame_ganadores_dia.rowconfigure(0, weight=1)
        self.frame_ganadores_dia.columnconfigure(0, weight=1)

        self.tree_ganadores_dia = ttk.Treeview(self.frame_ganadores_dia, columns=("Sorteo", "Ganador"), show="headings")
        self.tree_ganadores_dia.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.tree_ganadores_dia.heading("Sorteo", text="Sorteo")
        self.tree_ganadores_dia.heading("Ganador", text="Número")
        self.tree_ganadores_dia.column("Sorteo", width=100, anchor="center")
        self.tree_ganadores_dia.column("Ganador", width=120, anchor="center")

        # --- Estado de la venta --- (Lo movemos al final para que no interrumpa el PanedWindow)
        self.frame_estado = ttk.LabelFrame(self.tab_ventas, text="Estado de Venta")
        self.frame_estado.grid(row=1, column=0, columnspan=3, padx=15, pady=5, sticky="ew") # row=1, debajo del PanedWindow
        self.lbl_estado = ttk.Label(self.frame_estado, text="Listo para vender...", wraplength=400)
        self.lbl_estado.pack(padx=10, pady=5, fill="x")

     
        # --- Lógica de persistencia de posiciones de PanedWindow ---
        sash_positions_json = cargar_configuracion_ui_db('ventas_paned_sash_positions')
        if sash_positions_json:
            try:
                sash_positions = json.loads(sash_positions_json)
                if isinstance(sash_positions, list) and len(sash_positions) == len(self.ventas_paned_window.panes()) - 1:
                    self.root.after(100, lambda: self.aplicar_posiciones_paned(sash_positions))
            except json.JSONDecodeError as e:
                print(f"Error al decodificar JSON de posiciones de PanedWindow: {e}")

       
       
        # Guardado automático periódico
        self._ultimas_posiciones_paned = []
        self._paned_sin_cambios = 0

        def verificar_paned_positions():
            try:
                self.root.update_idletasks()
                total_width = self.ventas_paned_window.winfo_width()

                if total_width <= 1:
                    print("⏳ PanedWindow aún no tiene ancho, reintentando...")
                    self.root.after(1000, verificar_paned_positions)
                    return

                frames = self.ventas_paned_window.panes()
                if len(frames) < 3:
                    print("❌ No se detectaron 3 columnas para el paned window.")
                    self.root.after(1000, verificar_paned_positions)
                    return

                proporciones = []
                for frame in frames:
                    ancho = self.root.nametowidget(frame).winfo_width()
                    if ancho == 0:
                        print("⚠️ Uno de los frames tiene ancho 0, reintentando...")
                        self.root.after(1000, verificar_paned_positions)
                        return
                    proporciones.append(round(ancho / total_width, 4))

                # Convertimos proporciones acumuladas en posiciones de sashes
                posiciones = [round(sum(proporciones[:i+1]), 4) for i in range(len(proporciones) - 1)]

                if posiciones != getattr(self, 'ventas_paned_positions', []):
                    self.ventas_paned_positions = posiciones
                    guardar_configuracion_ui_db('ventas_paned_sash_positions', json.dumps(posiciones))
                    print(f"💾 Posiciones actualizadas del PanedWindow: {posiciones}")

                self.root.after(1000, verificar_paned_positions)

            except Exception as e:
                print(f"❌ Error en verificar_paned_positions: {e}")
                self.root.after(1000, verificar_paned_positions)



    def guardar_distribucion_manual(self):
        self.root.update_idletasks()
        total_width = self.ventas_paned_window.winfo_width()

        if total_width <= 1:
            print("⏳ PanedWindow aún no está listo, espera para guardar.")
            self.root.after(300, self.guardar_distribucion_manual)
            return

        # Medimos directamente los anchos de los frames dentro del paned window
        frames = self.ventas_paned_window.panes()
        if len(frames) < 3:
            print("❌ No se encontraron las 3 columnas del paned window.")
            return

        proporciones = []
        for frame in frames:
            ancho = self.root.nametowidget(frame).winfo_width()
            if ancho == 0:
                print("❌ Uno de los frames tiene ancho 0, no se puede guardar.")
                return
            proporciones.append(round(ancho / total_width, 4))

        # Calculamos los sashes como suma acumulada
        posiciones = [round(sum(proporciones[:i+1]), 4) for i in range(len(proporciones) - 1)]
        guardar_configuracion_ui_db('ventas_paned_sash_positions', json.dumps(posiciones))
        print(f"💾 Distribución manual guardada (con widths): {posiciones}")
        messagebox.showinfo("Distribución Guardada", f"✅ Distribución guardada:\n{posiciones}")




    def restaurar_distribucion_predeterminada(self):
        predeterminado = [0.25, 0.65]  # Ajusta estos valores si quieres un layout diferente
        guardar_configuracion_ui_db('ventas_paned_sash_positions', json.dumps(predeterminado))
        self.aplicar_posiciones_paned(predeterminado)
        messagebox.showinfo("Distribución Restaurada", "♻️ Distribución predeterminada aplicada.")

    
    def aplicar_posiciones_paned(self, positions):
        self.root.update_idletasks()
        total_width = self.ventas_paned_window.winfo_width()

        if total_width <= 1:
            print("⏳ Aún no hay ancho para aplicar posiciones, reintentando...")
            self.root.after(300, lambda: self.aplicar_posiciones_paned(positions))
            return

        try:
            for i, pos_frac in enumerate(positions):
                x = int(pos_frac * total_width)
                self.ventas_paned_window.sashpos(i, x)
            print(f"📐 Posiciones aplicadas al PanedWindow: {positions}")
        except Exception as e:
            print(f"❌ Error al aplicar posiciones: {e}")

   
    def guardar_posiciones_paned(self, event=None):
        """Guarda las posiciones de los divisores del PanedWindow."""
        positions = []
        total_width = self.ventas_paned_window.winfo_width()

        panes = self.ventas_paned_window.panes()
        num_sashes = len(panes) - 1

        if total_width <= 1 or num_sashes < 1:
            return  # Evitar si no hay tamaño o divisores disponibles

        for i in range(num_sashes):
            try:
                x_coord, _ = self.ventas_paned_window.sash_coord(i)
                positions.append(x_coord / total_width)
            except Exception as e:
                print(f"⚠️ No se pudo obtener sash {i}: {e}")

        guardar_configuracion_ui_db('ventas_paned_sash_positions', json.dumps(positions))


    def persistir_anchos_treeview(self, treeview_widget, clave_sqlite, columnas):
        """
        Guarda y restaura anchos de columnas de un Treeview usando la tabla ui_configuracion.
        - treeview_widget: el widget Treeview
        - clave_sqlite: la clave única para guardar en la DB
        - columnas: lista de nombres de columnas que deseas persistir
        """
        # 1. Restaurar
        anchos_guardados = cargar_configuracion_ui_db(clave_sqlite)
        if anchos_guardados:
            try:
                datos = json.loads(anchos_guardados)
                for col in columnas:
                    if col in datos:
                        treeview_widget.column(col, width=datos[col])
            except Exception as e:
                print(f"❌ Error al restaurar columnas {clave_sqlite}: {e}")

        # 2. Variables internas para monitoreo
        treeview_widget._ultimos_anchos = {col: treeview_widget.column(col)["width"] for col in columnas}
        treeview_widget._ciclos_sin_cambios = 0

        def verificar():
            try:
                nuevos = {col: treeview_widget.column(col)["width"] for col in columnas}
                if nuevos != treeview_widget._ultimos_anchos:
                    guardar_configuracion_ui_db(clave_sqlite, json.dumps(nuevos))
                    treeview_widget._ultimos_anchos = nuevos
                    treeview_widget._ciclos_sin_cambios = 0
                    print(f"💾 Anchos guardados para {clave_sqlite}: {nuevos}")
                else:
                    treeview_widget._ciclos_sin_cambios += 1

                if treeview_widget._ciclos_sin_cambios < 20:
                    self.root.after(1000, verificar)
            except Exception as e:
                print(f"❌ Error al verificar cambios en columnas {clave_sqlite}: {e}")

        self.root.after(1000, verificar)
        


    def actualizar_historial_treeview(self):
        numero = self.numero_busqueda_var.get().zfill(2)
        if not numero.isdigit() or not (0 <= int(numero) <= 99):
            messagebox.showwarning("Número inválido", "Ingrese un número entre 00 y 99.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT COUNT(*), SUM(apuesta), SUM(premio_potencial), MAX(fecha_hora)
                FROM ventas
                WHERE numero_loteria = ?
            ''', (numero,))
            total_ventas = cursor.fetchone()

            cursor.execute('''
                SELECT COUNT(*) FROM resultados_sorteo WHERE numero_ganador = ?
            ''', (numero,))
            veces_ganador = cursor.fetchone()[0]

            resumen = [
                ("Veces vendido", total_ventas[0] or 0),
                ("Total apostado", f"C${total_ventas[1] or 0:,}"),
                ("Premio potencial", f"C${total_ventas[2] or 0:,}"),
                ("Última venta", total_ventas[3] or "N/A"),
                ("Veces como ganador", veces_ganador)
            ]

            self.tree_historial.delete(*self.tree_historial.get_children())
            for campo, valor in resumen:
                self.tree_historial.insert("", "end", values=(f"{campo}: {valor}",))

        except Exception as e:
            messagebox.showerror("Error al buscar", f"Ocurrió un error: {e}")
        finally:
            conn.close()


    def cambiar_tema(self):
        nuevo = self.tema_actual_var.get()
        if nuevo in self.style.theme_names():
            self.style.theme_use(nuevo)
            actualizar_tema_db(nuevo)
            messagebox.showinfo("Tema Aplicado", f"Tema '{nuevo}' aplicado.")
        else:
            messagebox.showerror("Error", "Tema no válido.")


    def crear_widgets_tab_graficos(self):
        # --- Panel de Filtros y Visibilidad ---
        filtros_frame = ttk.LabelFrame(self.tab_graficos, text="Controles de Visualización y Filtros")
        filtros_frame.pack(fill="x", padx=10, pady=10)

        # --- Sección desplazable para los gráficos ---
        canvas_frame = tk.Frame(self.tab_graficos)
        canvas_frame.pack(fill="both", expand=True)

        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def ajustar_ancho_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", ajustar_ancho_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Guardar referencia al frame donde se dibujarán los gráficos
        self.graficos_container = scrollable_frame


        # Tipo de período
        self.tipo_periodo_graficos = tk.StringVar(value="diario")
        ttk.Label(filtros_frame, text="Tipo de Período:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        periodo_combo = ttk.Combobox(filtros_frame, textvariable=self.tipo_periodo_graficos, values=["Diario", "Semanal", "Mensual", "Por fecha"], state="readonly", width=12)
        periodo_combo.grid(row=0, column=1, padx=5, pady=5)

        # Fecha inicio / fin
        self.fecha_inicio_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        self.fecha_fin_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        self.date_inicio_entry = DateEntry(filtros_frame, date_pattern="yyyy-mm-dd", textvariable=self.fecha_inicio_var, width=12)
        self.date_fin_entry = DateEntry(filtros_frame, date_pattern="yyyy-mm-dd", textvariable=self.fecha_fin_var, width=12)

        # Mes y año
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        años = [str(y) for y in range(datetime.now().year - 5, datetime.now().year + 2)]
        self.mes_grafico_var = tk.StringVar(value=meses[datetime.now().month - 1])
        self.anio_grafico_var = tk.StringVar(value=str(datetime.now().year))
        self.combo_mes = ttk.Combobox(filtros_frame, textvariable=self.mes_grafico_var, values=meses, state="readonly", width=10)
        self.combo_anio = ttk.Combobox(filtros_frame, textvariable=self.anio_grafico_var, values=años, state="readonly", width=6)

        # Checkboxes de selección de gráficos
        self.ver_top5 = tk.BooleanVar(value=True)
        self.ver_sorteos = tk.BooleanVar(value=True)
        self.ver_apuestas_vs_premios = tk.BooleanVar(value=True)
        ttk.Label(filtros_frame, text="Gráficos a Mostrar:").grid(row=0, column=2, padx=10, sticky="e")
        ttk.Checkbutton(filtros_frame, text="Top 5", variable=self.ver_top5).grid(row=0, column=3, padx=2)
        ttk.Checkbutton(filtros_frame, text="Sorteos", variable=self.ver_sorteos).grid(row=0, column=4, padx=2)
        ttk.Checkbutton(filtros_frame, text="Apuestas vs Premios", variable=self.ver_apuestas_vs_premios).grid(row=0, column=5, padx=2)

        # Botón para aplicar filtros
        btn_aplicar_filtros = ttk.Button(filtros_frame, text="Aplicar Filtros", style="Accent.TButton", command=self.actualizar_graficos_filtrados)
        btn_aplicar_filtros.grid(row=0, column=6, padx=10)

        # Función para alternar visibilidad de controles
        def mostrar_controles_dinamicos(event=None):
            self.date_inicio_entry.grid_remove()
            self.date_fin_entry.grid_remove()
            self.combo_mes.grid_remove()
            self.combo_anio.grid_remove()

            if self.tipo_periodo_graficos.get() == "por_fecha":
                ttk.Label(filtros_frame, text="Inicio:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
                self.date_inicio_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")
                ttk.Label(filtros_frame, text="Fin:").grid(row=1, column=2, padx=5, pady=2, sticky="w")
                self.date_fin_entry.grid(row=1, column=3, padx=5, pady=2, sticky="w")
            elif self.tipo_periodo_graficos.get() == "mensual":
                ttk.Label(filtros_frame, text="Mes:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
                self.combo_mes.grid(row=1, column=1, padx=5, pady=2, sticky="w")
                ttk.Label(filtros_frame, text="Año:").grid(row=1, column=2, padx=5, pady=2, sticky="w")
                self.combo_anio.grid(row=1, column=3, padx=5, pady=2, sticky="w")

        periodo_combo.bind("<<ComboboxSelected>>", mostrar_controles_dinamicos)
        mostrar_controles_dinamicos()

    def actualizar_graficos_filtrados(self):
            # ✅ Limpiar todos los gráficos previos del contenedor con scroll
            for widget in self.graficos_container.winfo_children():
                widget.destroy()

            tipo = self.tipo_periodo_graficos.get()
            fecha_ini = self.fecha_inicio_var.get()
            fecha_fin = self.fecha_fin_var.get()
            mes_nombre = self.mes_grafico_var.get()
            anio = self.anio_grafico_var.get()

            # Convertir mes a número
            meses_map = {
                "Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04",
                "Mayo": "05", "Junio": "06", "Julio": "07", "Agosto": "08",
                "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"
            }
            mes_numero = meses_map.get(mes_nombre)

            # --- Gráfico 1 ---
            if self.ver_top5.get():
                self.mostrar_top_5(tipo, fecha_ini, fecha_fin, mes_numero, anio)

            # --- Gráfico 2 ---
            if self.ver_sorteos.get():
                self.mostrar_sorteos_semanales(tipo, fecha_ini, fecha_fin, mes_numero, anio)

            # --- Gráfico 3 ---
            if self.ver_apuestas_vs_premios.get():
                self.mostrar_apuestas_vs_premios(tipo, fecha_ini, fecha_fin, mes_numero, anio)



    def mostrar_top_5(self, tipo, fecha_ini, fecha_fin, mes, anio):
        frame = ttk.LabelFrame(self.graficos_container, text="...")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        fig = plt.Figure(figsize=(6, 3), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_title("Top 5 por período seleccionado")
        ax.set_xlabel("Número")
        ax.set_ylabel("Total Apostado")

        # Query base adaptada
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        where = []
        params = []

        if tipo == "diario":
            hoy = datetime.now().strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia = ?")
            params.append(hoy)
        elif tipo == "semanal":
            lunes = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia >= ?")
            params.append(lunes)
        elif tipo == "por_fecha":
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_ini, fecha_fin])
        elif tipo == "mensual" and mes and anio:
            fecha_i = f"{anio}-{mes}-01"
            fecha_f = f"{anio}-{mes}-31"
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_i, fecha_f])

        query = "SELECT numero_loteria, SUM(apuesta) FROM ventas"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " GROUP BY numero_loteria ORDER BY SUM(apuesta) DESC LIMIT 5"

        cursor.execute(query, tuple(params))
        data = cursor.fetchall()
        conn.close()

        if data:
            numeros, totales = zip(*data)
            x = range(len(numeros))
            ax.bar(x, totales, color="#4CAF50")
            ax.set_xticks(x)
            ax.set_xticklabels(numeros, rotation=45)
            fig.subplots_adjust(bottom=0.25)

        else:
            ax.text(0.5, 0.5, "Sin datos", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="gray")

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()



    def mostrar_sorteos_semanales(self, tipo, fecha_ini, fecha_fin, mes, anio):
        frame = ttk.LabelFrame(self.graficos_container, text="...")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        fig = plt.Figure(figsize=(6, 3), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_title("Sorteos más activos")
        ax.set_xlabel("Sorteo")
        ax.set_ylabel("Total Apostado")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        where = []
        params = []

        if tipo == "diario":
            hoy = datetime.now().strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia = ?")
            params.append(hoy)
        elif tipo == "semanal":
            lunes = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia >= ?")
            params.append(lunes)
        elif tipo == "por_fecha":
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_ini, fecha_fin])
        elif tipo == "mensual" and mes and anio:
            fecha_i = f"{anio}-{mes}-01"
            fecha_f = f"{anio}-{mes}-31"
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_i, fecha_f])

        query = "SELECT sorteo_hora, SUM(apuesta) FROM ventas"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " GROUP BY sorteo_hora ORDER BY sorteo_hora"

        cursor.execute(query, tuple(params))
        data = cursor.fetchall()
        conn.close()

        if data:
            sorteos, totales = zip(*data)
            x = range(len(sorteos))
            ax.bar(x, totales, color="#2196F3")
            ax.set_xticks(x)
            ax.set_xticklabels(sorteos, rotation=45)
            fig.subplots_adjust(bottom=0.25)

        else:
            ax.text(0.5, 0.5, "Sin datos", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="gray")

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()


    def mostrar_apuestas_vs_premios(self, tipo, fecha_ini, fecha_fin, mes, anio):
        frame = ttk.LabelFrame(self.graficos_container, text="...")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        fig = plt.Figure(figsize=(6, 3), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_title("Por Sorteo")
        ax.set_ylabel("Córdobas (C$)")
        ax.set_xlabel("Sorteo")

        # --- Obtener fechas
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        where = []
        params = []

        if tipo == "diario":
            hoy = datetime.now().strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia = ?")
            params.append(hoy)
        elif tipo == "semanal":
            lunes = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            where.append("venta_fecha_solo_dia >= ?")
            params.append(lunes)
        elif tipo == "por_fecha":
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_ini, fecha_fin])
        elif tipo == "mensual" and mes and anio:
            fecha_i = f"{anio}-{mes}-01"
            fecha_f = f"{anio}-{mes}-31"
            where.append("venta_fecha_solo_dia BETWEEN ? AND ?")
            params.extend([fecha_i, fecha_f])

        condicional = " WHERE " + " AND ".join(where) if where else ""

        # --- Total apostado
        query_apuestas = f'''
            SELECT sorteo_hora, SUM(apuesta)
            FROM ventas
            {condicional}
            GROUP BY sorteo_hora
        '''
        cursor.execute(query_apuestas, tuple(params))
        apuestas = dict(cursor.fetchall())

        # --- Total premios entregados
        query_premios = f'''
            SELECT v.sorteo_hora, SUM(v.premio_potencial)
            FROM ventas v
            JOIN resultados_sorteo r
                ON v.venta_fecha_solo_dia = r.fecha_sorteo
                AND v.sorteo_hora = r.hora_sorteo
                AND v.numero_loteria = r.numero_ganador
            {condicional}
            GROUP BY v.sorteo_hora
        '''
        cursor.execute(query_premios, tuple(params))
        premios = dict(cursor.fetchall())

        conn.close()

        sorteos = ['11 AM', '03 PM', '06 PM', '09 PM']
        totales_apuestas = [apuestas.get(s, 0) for s in sorteos]
        totales_premios = [premios.get(s, 0) for s in sorteos]

        if any(totales_apuestas) or any(totales_premios):
            bar_width = 0.35
            x = range(len(sorteos))
            ax.bar([i - bar_width/2 for i in x], totales_apuestas, width=bar_width, label='Apostado', color='#2196F3')
            ax.bar([i + bar_width/2 for i in x], totales_premios, width=bar_width, label='Premios', color='#FFC107')
            ax.set_xticks(list(x))
            ax.set_xticklabels(sorteos, rotation=45)
            fig.subplots_adjust(bottom=0.25)
            ax.legend()
        else:
            ax.text(0.5, 0.5, "No hay datos", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="gray")

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()




    def crear_widgets_tab_configuracion(self):
        # Frame para acciones principales (movido de la pestaña de ventas)
        self.frame_acciones = ttk.LabelFrame(self.tab_configuracion, text="Acciones Generales")
        self.frame_acciones.pack(padx=15, pady=10, fill="x", expand=True)
        
        # --- Frame para cambiar tema ---
        self.frame_selector_tema = ttk.LabelFrame(self.tab_configuracion, text="Tema de la Aplicación")
        self.frame_selector_tema.pack(padx=15, pady=10, fill="x", expand=True)

        ttk.Label(self.frame_selector_tema, text="Seleccionar Tema:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # Obtener todos los temas disponibles (nativos + azure si ya se cargó)
        temas_disponibles = list(self.style.theme_names())  # ['clam', 'alt', 'default', ...]
        self.tema_actual_var = tk.StringVar(value=self.style.theme_use())

        self.combo_temas = ttk.Combobox(
            self.frame_selector_tema,
            textvariable=self.tema_actual_var,
            values=temas_disponibles,
            state="readonly"
        )
        self.combo_temas.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_aplicar_tema = ttk.Button(
            self.frame_selector_tema,
            text="Aplicar Tema",
            command=self.cambiar_tema,
            style='Accent.TButton'
        )
        self.btn_aplicar_tema.grid(row=1, column=0, columnspan=2, pady=10)

        self.frame_selector_tema.columnconfigure(1, weight=1)


        # --- Nuevo: Frame para configurar el premio por cada 5 ---
        self.frame_config_premio = ttk.LabelFrame(self.tab_configuracion, text="Configurar Premio por C$1")
        self.frame_config_premio.pack(padx=15, pady=10, fill="x", expand=True)

        ttk.Label(self.frame_config_premio, text="Premio por cada C$1 apostados:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.premio_por_cordoba_var = tk.StringVar(value=str(obtener_premio_por_cordoba_db())) # Carga el valor actual
        self.entry_premio_por_cordoba = ttk.Entry(self.frame_config_premio, textvariable=self.premio_por_cordoba_var, font=("Arial", 11))
        self.entry_premio_por_cordoba.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_guardar_premio = ttk.Button(self.frame_config_premio, text="Guardar Premio", command=self.guardar_premio_por_cordoba)
        self.btn_guardar_premio.grid(row=1, column=0, columnspan=2, pady=10)

        self.frame_config_premio.columnconfigure(1, weight=1) # Permite que el campo de entrada se expanda
        
        self.btn_salir = ttk.Button(self.frame_acciones, text="Salir", command=self.root.quit)
        self.btn_salir.pack(pady=10, fill="x", padx=20)
        
        self.btn_cambiar_clave = ttk.Button(
        self.frame_acciones,
        text="Cambiar Clave de Acceso",
        command=self.mostrar_ventana_cambiar_clave
        )
        self.btn_cambiar_clave.pack(pady=10, fill="x", padx=20)

        # --- NUEVO: Controlar divisores manualmente ---
        frame_divisores = ttk.LabelFrame(self.tab_configuracion, text="Distribución de la Pestaña Ventas")
        frame_divisores.pack(padx=15, pady=10, fill="x", expand=True)

        ttk.Button(frame_divisores, text="📥 Guardar Distribución Actual", style="Accent.TButton",
                command=self.guardar_distribucion_manual).pack(padx=10, pady=5, fill="x")

        ttk.Button(frame_divisores, text="♻️ Restaurar Distribución Predeterminada", style="Accent.TButton",
                command=self.restaurar_distribucion_predeterminada).pack(padx=10, pady=5, fill="x")



        # Opcional: Centrar el contenido en la pestaña de configuración
        self.tab_configuracion.grid_columnconfigure(0, weight=1) # Make the column expandable
        self.tab_configuracion.grid_rowconfigure(0, weight=1)    # Make the row expandable




    def _set_initial_sorteo_selection_venta(self):
        """
        Determina el sorteo actual más cercano y lo selecciona como valor inicial
        para la pestaña de ventas.
        """
        now = datetime.now()
        current_hour = now.hour
        
        # Horas de corte de los sorteos (en formato 24h)
        sorteo_times = {
            '11 AM': 11,
            '03 PM': 15,
            '06 PM': 18,
            '09 PM': 21
        }
        
        # Ordenar los sorteos por hora
        sorted_sorteos = sorted(sorteo_times.items(), key=lambda item: item[1])
        
        selected_sorteo = None
        for sorteo_name, sorteo_hour in sorted_sorteos:
            if current_hour < sorteo_hour:
                selected_sorteo = sorteo_name
                break
        
        if selected_sorteo is None:
            # Si ya pasaron todos los sorteos del día, seleccionar el último (09 PM)
            selected_sorteo = '09 PM'
        
        self.sorteo_var.set(selected_sorteo)


    def crear_widgets_tab_sorteos(self):
        # Variables para la pestaña de sorteos

        # --- Frame para Registrar/Actualizar Ganador ---
        frame_registrar = ttk.LabelFrame(self.tab_sorteos, text="Registrar/Actualizar Número Ganador")
        frame_registrar.pack(padx=15, pady=10, fill="x")

        ttk.Label(frame_registrar, text="Fecha del Sorteo:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.date_entry_registro = DateEntry(frame_registrar, width=12, background='darkblue',
                                             foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.date_entry_registro.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # --- Radiobuttons para Sorteo en Gestión de Sorteos ---
        ttk.Label(frame_registrar, text="Sorteo:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.sorteo_registro_var = tk.StringVar()
        self.sorteo_registro_var.set('06 PM')
        
        self.sorteo_radio_frame_registro = ttk.Frame(frame_registrar)
        self.sorteo_radio_frame_registro.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        for i, sorteo in enumerate(self.sorteo_options_all):
            rb = ttk.Radiobutton(self.sorteo_radio_frame_registro, text=sorteo, variable=self.sorteo_registro_var, value=sorteo)
            rb.grid(row=0, column=i, padx=5, pady=2)
        
        self.sorteo_radio_frame_registro.grid_columnconfigure(0, weight=1)
        self.sorteo_radio_frame_registro.grid_columnconfigure(1, weight=1)
        self.sorteo_radio_frame_registro.grid_columnconfigure(2, weight=1)
        self.sorteo_radio_frame_registro.grid_columnconfigure(3, weight=1)
        # --- Fin de los Radiobuttons ---

        ttk.Label(frame_registrar, text="Número Ganador (00-99):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.ganador_numero_var = tk.StringVar()
        self.ganador_numero_entry = ttk.Entry(frame_registrar, textvariable=self.ganador_numero_var, width=10, font=("Arial", 12, "bold"))
        self.ganador_numero_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        # Enlazar la tecla Enter al campo de número ganador
        self.ganador_numero_entry.bind("<Return>", lambda event=None: self.registrar_ganador_gui())

        ttk.Button(frame_registrar, text="Registrar/Actualizar Ganador", command=self.registrar_ganador_gui, style='Accent.TButton').grid(row=3, column=0, columnspan=2, pady=10)

        frame_registrar.columnconfigure(1, weight=1)

        # --- Frame para Consultar Ganador ---
        frame_consultar = ttk.LabelFrame(self.tab_sorteos, text="Consultar Número Ganador")
        frame_consultar.pack(padx=15, pady=10, fill="x")

        ttk.Label(frame_consultar, text="Fecha a Consultar:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.date_entry_consulta = DateEntry(frame_consultar, width=12, background='darkblue',
                                            foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.date_entry_consulta.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # --- Radiobuttons para Sorteo en Consultar Ganador ---
        ttk.Label(frame_consultar, text="Sorteo a Consultar:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.sorteo_consulta_var = tk.StringVar()
        self.sorteo_consulta_var.set('06 PM')
        
        self.sorteo_radio_frame_consulta = ttk.Frame(frame_consultar)
        self.sorteo_radio_frame_consulta.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        for i, sorteo in enumerate(self.sorteo_options_all):
            rb = ttk.Radiobutton(self.sorteo_radio_frame_consulta, text=sorteo, variable=self.sorteo_consulta_var, value=sorteo)
            rb.grid(row=0, column=i, padx=5, pady=2)

        self.sorteo_radio_frame_consulta.grid_columnconfigure(0, weight=1)
        self.sorteo_radio_frame_consulta.grid_columnconfigure(1, weight=1)
        self.sorteo_radio_frame_consulta.grid_columnconfigure(2, weight=1)
        self.sorteo_radio_frame_consulta.grid_columnconfigure(3, weight=1)
        # --- Fin de los Radiobuttons ---

        ttk.Button(frame_consultar, text="Consultar Ganador", command=self.consultar_ganador_gui).grid(row=2, column=0, padx=5, pady=10, sticky="ew")
        self.lbl_resultado_consulta = ttk.Label(frame_consultar, text="Número Ganador: --", font=("Arial", 12, "bold"))
        self.lbl_resultado_consulta.grid(row=2, column=1, padx=5, pady=10, sticky="ew")
        
        frame_consultar.columnconfigure(1, weight=1)

        # --- Historial de Ganadores ---
        frame_historial = ttk.LabelFrame(self.tab_sorteos, text="Últimos Ganadores Registrados")
        frame_historial.pack(padx=15, pady=10, fill="both", expand=True)

        self.tree_ganadores = ttk.Treeview(frame_historial, columns=("Fecha", "Sorteo", "Número Ganador"), show="headings")
        self.tree_ganadores.pack(padx=5, pady=5, fill="both", expand=True)
        

        self.tree_ganadores.heading("Fecha", text="Fecha")
        self.tree_ganadores.heading("Sorteo", text="Sorteo")
        self.tree_ganadores.heading("Número Ganador", text="Número Ganador")

        self.tree_ganadores.column("Fecha", width=120, anchor="center")
        self.tree_ganadores.column("Sorteo", width=80, anchor="center")
        self.tree_ganadores.column("Número Ganador", width=120, anchor="center")
    
    def crear_widgets_tab_reportes(self):
        # Variables para la pestaña de reportes
        self.report_type = tk.StringVar(value="diario")
        # <<< CAMBIO INICIADO: Crear variables para fecha de inicio y fin.
        self.report_start_date_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        self.report_end_date_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        # <<< CAMBIO FINALIZADO
        self.report_data_type_var = tk.StringVar(value="Ventas") # Nuevo: "Ventas" o "Ganadores"
        
        # Diccionario para mapear números de mes a nombres de mes
        self.meses_map = {
            "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
            "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
            "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
        }
        self.meses_map_reverse = {v: k for k, v in self.meses_map.items()} # Para obtener el número desde el nombre
        
        # Mes actual en letras por defecto
        current_month_num = datetime.now().strftime('%m')
        self.report_month_var = tk.StringVar(value=self.meses_map[current_month_num]) 
        
        self.report_year_var = tk.StringVar(value=str(datetime.now().year))   # Año actual por defecto
        self.report_sorteo_var = tk.StringVar(value="Todos")
        self.sorteo_options_reportes = ('Todos',) + self.sorteo_options_all

        # Frame de Controles de Reporte
        self.frame_controles_reporte = ttk.LabelFrame(self.tab_reportes, text="Filtros de Reporte")
        self.frame_controles_reporte.grid(row=0, column=0, padx=15, pady=10, sticky="ew")
        self.tab_reportes.columnconfigure(0, weight=1) # Allow this column to expand


        # Radiobuttons para TIPO DE REPORTE (Ventas o Ganadores)
        ttk.Label(self.frame_controles_reporte, text="Datos a Reportar:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(self.frame_controles_reporte, text="Ventas", variable=self.report_data_type_var, value="Ventas", command=self.generar_reporte_gui).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(self.frame_controles_reporte, text="Ganadores", variable=self.report_data_type_var, value="Ganadores", command=self.generar_reporte_gui).grid(row=0, column=2, padx=5, pady=5, sticky="w")

        # Radiobuttons para TIPO DE PERÍODO (Diario, Semanal, Mensual, Por Fecha)
        ttk.Label(self.frame_controles_reporte, text="Tipo de Período:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(self.frame_controles_reporte, text="Diario", variable=self.report_type, value="diario", command=self.on_report_type_change).grid(row=1, column=1, padx=5, pady=5, sticky="w") 
        ttk.Radiobutton(self.frame_controles_reporte, text="Semanal", variable=self.report_type, value="semanal", command=self.on_report_type_change).grid(row=1, column=2, padx=5, pady=5, sticky="w") 
        ttk.Radiobutton(self.frame_controles_reporte, text="Mensual", variable=self.report_type, value="mensual", command=self.on_report_type_change).grid(row=1, column=3, padx=5, pady=5, sticky="w") 
        ttk.Radiobutton(self.frame_controles_reporte, text="Por Rango de Fechas", variable=self.report_type, value="por_fecha", command=self.on_report_type_change).grid(row=1, column=4, padx=5, pady=5, sticky="w") 

        # <<< CAMBIO INICIADO: Crear widgets para fecha de inicio y fin.
        self.lbl_fecha_inicial = ttk.Label(self.frame_controles_reporte, text="Fecha Inicial:")
        self.date_entry_reporte_inicio = DateEntry(self.frame_controles_reporte, width=12, background='darkblue',
                                             foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd',
                                             textvariable=self.report_start_date_var)

        self.lbl_fecha_final = ttk.Label(self.frame_controles_reporte, text="Fecha Final:")
        self.date_entry_reporte_fin = DateEntry(self.frame_controles_reporte, width=12, background='darkblue',
                                             foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd',
                                             textvariable=self.report_end_date_var)
        # <<< CAMBIO FINALIZADO

        # --- Widgets para selección de mes y año (Combobox) ---
        self.lbl_mes_reporte = ttk.Label(self.frame_controles_reporte, text="Mes:") # Etiqueta correcta para el mes
        self.lbl_year_reporte = ttk.Label(self.frame_controles_reporte, text="Año:")

        # Ahora el ComboBox de meses usará los nombres de los meses
        meses_nombres = list(self.meses_map.values())
        self.combo_mes_reporte = ttk.Combobox(self.frame_controles_reporte, textvariable=self.report_month_var, values=meses_nombres, state="readonly", width=10)
        
        current_year = datetime.now().year
        años = [str(y) for y in range(current_year - 5, current_year + 2)] # Rango de 5 años atrás a 1 año adelante
        self.combo_year_reporte = ttk.Combobox(self.frame_controles_reporte, textvariable=self.report_year_var, values=años, state="readonly", width=7)

        # --- Radiobuttons para Sorteo en Reportes ---
        self.lbl_sorteo_reporte = ttk.Label(self.frame_controles_reporte, text="Sorteo:") # Nueva etiqueta para Sorteo
        self.sorteo_radio_frame_reportes = ttk.Frame(self.frame_controles_reporte)
        for i, sorteo in enumerate(self.sorteo_options_reportes):
            rb = ttk.Radiobutton(self.sorteo_radio_frame_reportes, text=sorteo, variable=self.report_sorteo_var, value=sorteo)
            rb.grid(row=0, column=i, padx=5, pady=2)
            self.sorteo_radio_frame_reportes.grid_columnconfigure(i, weight=1)
        
        # Columna de la derecha se expande para el combo de año (si aplica)
        self.frame_controles_reporte.grid_columnconfigure(4, weight=1) 

        self.btn_generar_reporte = ttk.Button(self.frame_controles_reporte, text="Generar Reporte", command=self.generar_reporte_gui)

        # Área de Texto para el Reporte
        self.report_text_area = scrolledtext.ScrolledText(self.tab_reportes, wrap=tk.WORD, width=80, height=20, font=("Courier New", 9)) # Fuente monoespaciada para mejor alineación en texto
        self.report_text_area.grid(row=1, column=0, padx=15, pady=10, sticky="nsew")
        self.tab_reportes.rowconfigure(1, weight=1) # Make this row expand vertically

        # Botones de Exportar/Imprimir
        self.frame_export_print = ttk.Frame(self.tab_reportes)
        self.frame_export_print.grid(row=2, column=0, pady=5, sticky="ew")
              
        ttk.Button(self.frame_export_print, text="Exportar a PDF", command=self.exportar_reporte_a_pdf, style='Accent.TButton').pack(side=tk.LEFT, padx=10, expand=True, fill="x")
        ttk.Button(self.frame_export_print, text="Imprimir Reporte", command=self.imprimir_reporte_gui).pack(side=tk.LEFT, padx=10, expand=True, fill="x")

        # Llamar a la función para configurar la visibilidad inicial
        self.on_report_type_change()

    def on_report_type_change(self):
        """Ajusta la visibilidad y posición de los selectores de fecha/mes/año y el botón de reporte."""
        report_type = self.report_type.get()

        # <<< CAMBIO INICIADO: Ocultar los widgets de rango de fechas.
        self.lbl_fecha_inicial.grid_remove()
        self.date_entry_reporte_inicio.grid_remove()
        self.lbl_fecha_final.grid_remove()
        self.date_entry_reporte_fin.grid_remove()
        # <<< CAMBIO FINALIZADO
        self.lbl_mes_reporte.grid_remove()
        self.combo_mes_reporte.grid_remove()
        self.lbl_year_reporte.grid_remove()
        self.combo_year_reporte.grid_remove()
        self.lbl_sorteo_reporte.grid_remove() # Ocultar la etiqueta de sorteo
        self.sorteo_radio_frame_reportes.grid_remove() # Ocultar los radiobuttons de sorteo

        # La fila de "Datos a Reportar" es la 0.
        # La fila de "Tipo de Período" es la 1.
        # current_row indicará la próxima fila disponible después de la fila 1.
        current_row = 2 

        # <<< CAMBIO INICIADO: Mostrar los widgets de rango de fechas si es necesario.
        if report_type == "por_fecha":
            self.lbl_fecha_inicial.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
            self.date_entry_reporte_inicio.grid(row=current_row, column=1, padx=5, pady=5, sticky="ew")
            self.lbl_fecha_final.grid(row=current_row, column=2, padx=5, pady=5, sticky="w")
            self.date_entry_reporte_fin.grid(row=current_row, column=3, padx=5, pady=5, sticky="ew")
            current_row += 1 
        # <<< CAMBIO FINALIZADO
        elif report_type == "mensual":
            self.lbl_mes_reporte.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
            self.combo_mes_reporte.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
            self.lbl_year_reporte.grid(row=current_row, column=2, padx=5, pady=5, sticky="w")
            self.combo_year_reporte.grid(row=current_row, column=3, padx=5, pady=5, sticky="w")
            current_row += 1 

        # Colocar la etiqueta "Sorteo:" y los radiobuttons de sorteo en la siguiente fila.
        self.lbl_sorteo_reporte.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
        self.sorteo_radio_frame_reportes.grid(row=current_row, column=1, columnspan=4, padx=5, pady=5, sticky="ew")
        
        current_row += 1 # Avanzar a la siguiente fila para el botón

        # Colocar el botón "Generar Reporte"
        self.btn_generar_reporte.grid(row=current_row, column=0, columnspan=5, pady=15)
        self.generar_reporte_gui() # Regenerar el reporte al cambiar los filtros

    def on_tab_change(self, event):
        pestaña_actual = self.notebook.tab(self.notebook.select(), "text")
        if pestaña_actual == "Ventas":
            self.actualizar_resumen_ventas_dia()
        elif pestaña_actual == "Reportes":
            self.actualizar_listas_reportes()
        elif pestaña_actual == "Gráficos":
            self.actualizar_graficos_filtrados()



    def update_top_info(self, *args):
        """Actualiza la fecha y el sorteo en la parte superior de la ventana principal."""
        self.current_date_var.set(datetime.now().strftime('%d-%m-%Y'))
        selected_sorteo = self.sorteo_var.get()
        if selected_sorteo:
            self.current_sorteo_var.set(selected_sorteo)
        else:
            self.current_sorteo_var.set("N/A")

    def actualizar_estado(self, mensaje, is_error=False):
        """Actualiza el mensaje de estado en la GUI (para la pestaña de ventas)."""
        self.lbl_estado.config(text=mensaje)
        if is_error:
            self.lbl_estado.config(foreground="red")
        else:
            self.lbl_estado.config(foreground="black")

    def actualizar_premio_calculado(self, *args):
        """Calcula y actualiza el premio potencial en la GUI (para la pestaña de ventas)."""
        try:
            apuesta = int(self.apuesta_var.get())
            premio = calcular_premio(apuesta)
            if premio > 0:
                self.premio_calculado_var.set(f"C${premio}")
                self.lbl_premio_calculado.config(foreground="green")
            else:
                self.premio_calculado_var.set("C$0")
                self.lbl_premio_calculado.config(foreground="red")
        except ValueError:
            self.premio_calculado_var.set("C$0")
            self.lbl_premio_calculado.config(foreground="red")


    def vender_numero_gui(self):
        """Maneja la lógica de venta desde la GUI (para la pestaña de ventas)."""
        try:
            numero_str = self.numero_var.get()
            numero = int(numero_str)
            if not (0 <= numero <= 99):
                raise ValueError("Número inválido. Debe ser entre 00 y 99.")

            apuesta_str = self.apuesta_var.get()
            
            # --- INICIO DE MODIFICACIÓN ---
            # 1. Convertir a float primero para manejar entradas como "1.0"
            try:
                apuesta_float = float(apuesta_str)
            except ValueError:
                raise ValueError("Cantidad inválida. Debe ser un número.")
                
            # 2. Validar que la apuesta sea un número entero (sin decimales) o .0
            if apuesta_float != int(apuesta_float):
                raise ValueError("Cantidad inválida. La apuesta debe ser un número entero. Por favor, ingrese un valor sin decimales (ej. 1, 5, 10).")
                
            apuesta = int(apuesta_float) # Ahora apuesta es un entero

            # 3. Validar que la apuesta sea positiva
            if apuesta <= 0:
                raise ValueError("Cantidad inválida. Debe ser un número positivo.")
                
            # 4. Obtener el monto mínimo de venta de la base de datos
            monto_minimo = obtener_monto_minimo_venta_db() # Asegúrate de que esta función esté definida

            # 5. Validar la apuesta contra el monto mínimo
            if apuesta < monto_minimo:
                raise ValueError(f"Cantidad inválida. La apuesta mínima permitida es de C${monto_minimo:.0f}.")
            
            # --- FIN DE MODIFICACIÓN ---

            sorteo_seleccionado = self.sorteo_var.get()
            if not sorteo_seleccionado:
                raise ValueError("Debe seleccionar un sorteo.")

            premio = calcular_premio(apuesta)

            confirm = messagebox.askyesno(
                "Confirmar Venta",
                f"¿Desea vender el número {formatear_numero_loteria(numero)} para el Sorteo de {sorteo_seleccionado} con C${apuesta} (premio potencial C${premio})?"
            )
            if confirm:
                exito, mensaje = registrar_venta_db(numero, apuesta, premio, sorteo_seleccionado)
                if exito:
                    self.actualizar_estado(mensaje)
                    self.actualizar_resumen_ventas_dia()  # ✅ Añadir esta línea
                    self.numero_var.set("")
                    self.apuesta_var.set("")
                    self.premio_calculado_var.set("C$0")
                    self.numero_entry.focus_set()

                else:
                    self.actualizar_estado(mensaje, is_error=True)
                    messagebox.showerror("Error de Venta", mensaje)
            else:
                self.actualizar_estado("Venta cancelada por el usuario.")

        except ValueError as e:
            mensaje = str(e)
            self.actualizar_estado(f"Error de entrada: {mensaje}", is_error=True)
            messagebox.showerror("Error de Entrada", mensaje)

            # Aquí puedes decidir qué campo limpiar o enfocar, basado en el mensaje de error
            if "Número inválido" in mensaje:
                self.numero_var.set("")
                self.numero_entry.focus_set()
            elif "Cantidad inválida" in mensaje:
                self.apuesta_var.set("")  # Limpia el campo de apuesta
                self.apuesta_entry.focus_set()

        except Exception as e:
            self.actualizar_estado(f"Ocurrió un error inesperado: {e}", is_error=True)
            messagebox.showerror("Error", f"Ocurrió un error inesperado: {e}")

    # --- AQUI ES UN BUEN LUGAR PARA PEGAR ejecutar_busqueda_historial ---
    def ejecutar_busqueda_historial(self, initial_message=None):
        """
        Muestra un resumen del historial de ventas y ganadores para el número ingresado
        en el Treeview.
        """
        # Limpia el Treeview antes de insertar nuevos datos
        self.tree_historial_resumen.delete(*self.tree_historial_resumen.get_children())

        # Si hay un mensaje inicial (como el del número más vendido), lo insertamos primero
        if initial_message:
            self.tree_historial_resumen.insert("", "end", values=("Info", initial_message))
            self.tree_historial_resumen.insert("", "end", values=("", "")) # Línea en blanco para separar

        numero_a_buscar_str = self.numero_busqueda_var.get().strip()

        if not numero_a_buscar_str:
            self.tree_historial_resumen.insert("", "end", values=("Estado", "Por favor, ingrese un número para buscar."))
            return

        # Validar que sea un número y esté en el rango 00-99
        if not numero_a_buscar_str.isdigit() or not (0 <= int(numero_a_buscar_str) <= 99):
            self.tree_historial_resumen.insert("", "end", values=("Estado", "Ingrese un número de lotería válido (00-99)."))
            return
        
        numero_formateado = formatear_numero_loteria(int(numero_a_buscar_str))

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            # --- APLICAR FILTRO DE PERÍODO SELECCIONADO ---
            tipo_periodo = self.periodo_resumen_var.get()
            where = "WHERE numero_loteria = ?"
            params = [numero_formateado]

            if tipo_periodo == "diario":
                where += " AND venta_fecha_solo_dia = ?"
                params.append(datetime.now().strftime('%Y-%m-%d'))

            elif tipo_periodo == "semanal":
                lunes = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
                where += " AND venta_fecha_solo_dia >= ?"
                params.append(lunes)

            elif tipo_periodo == "mensual":
                meses_map = {
                    "Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04",
                    "Mayo": "05", "Junio": "06", "Julio": "07", "Agosto": "08",
                    "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"
                }
                mes = meses_map.get(self.mes_resumen_var.get(), "01")
                anio = self.anio_resumen_var.get()
                fecha_ini = f"{anio}-{mes}-01"
                fecha_fin = f"{anio}-{mes}-31"
                where += " AND venta_fecha_solo_dia BETWEEN ? AND ?"
                params.extend([fecha_ini, fecha_fin])

            elif tipo_periodo == "por período":
                fecha_ini = self.fecha_ini_resumen_var.get()
                fecha_fin = self.fecha_fin_resumen_var.get()
                where += " AND venta_fecha_solo_dia BETWEEN ? AND ?"
                params.extend([fecha_ini, fecha_fin])

            # Ejecutar consulta con filtros aplicados
            cursor.execute(f'''
                SELECT COUNT(*), SUM(apuesta), SUM(premio_potencial), MAX(fecha_hora)
                FROM ventas
                {where}
            ''', params)
            total_ventas = cursor.fetchone()

            # Obtener cuántas veces ha sido ganador ese número
            cursor.execute('''
                SELECT COUNT(*) FROM resultados_sorteo WHERE numero_ganador = ?
            ''', (numero_formateado,))
            veces_ganador = cursor.fetchone()[0]

            # Preparar los datos para el Treeview en el formato deseado
            resumen_data = [
                ("Número buscado", numero_formateado),
                ("Veces vendido", total_ventas[0] if total_ventas[0] is not None else 0),
                ("Total apostado", f"C${total_ventas[1]:,.2f}" if total_ventas[1] is not None else "C$0.00"),
                ("Premio Potencial", f"C${total_ventas[2]:,.2f}" if total_ventas[2] is not None else "C$0.00"),
                ("Última venta", total_ventas[3] if total_ventas[3] else "N/A"),
                ("Veces ganador", veces_ganador)
            ]
            
            # Mapear a los nombres que el usuario pidió:
            # "Sorteos" -> "Veces ganador" (el número que ha salido ganador)
            # "Apuesta" -> "Total apostado"
            # "Ganancia" -> "Premio Potencial"
            # "Ultima venta" -> "Última venta"
            
            # Formato final para el Treeview
            display_data = [
                ("Sorteos (Veces Ganador)", resumen_data[5][1]), # 'Veces ganador'
                ("Apuesta Total", resumen_data[2][1]), # 'Total apostado'
                ("Ganancia Potencial", resumen_data[3][1]), # 'Premio Potencial'
                ("Última Venta", resumen_data[4][1]) # 'Última venta'
            ]

            if total_ventas[0] is None and veces_ganador == 0: # Si no hay ventas ni es ganador
                self.tree_historial_resumen.insert("", "end", values=("Info", f"No hay datos para el número {numero_formateado}."))
            else:
                for campo, valor in display_data:
                    self.tree_historial_resumen.insert("", "end", values=(campo, valor))

        except Exception as e:
            self.tree_historial_resumen.insert("", "end", values=("Error", f"Ocurrió un error al buscar: {e}"))
            print(f"Error en ejecutar_busqueda_historial: {e}")
        finally:
            conn.close()


    def buscar_historial_numero(self):
        numero = self.numero_busqueda_var.get().zfill(2)
        if not numero.isdigit() or not (0 <= int(numero) <= 99):
            messagebox.showwarning("Número inválido", "Ingrese un número entre 00 y 99.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            # Total de ventas
            cursor.execute('''
                SELECT COUNT(*), SUM(apuesta), SUM(premio_potencial), MAX(fecha_hora)
                FROM ventas
                WHERE numero_loteria = ?
            ''', (numero,))
            total_ventas = cursor.fetchone()

            # Veces que ha sido ganador
            cursor.execute('''
                SELECT COUNT(*)
                FROM resultados_sorteo
                WHERE numero_ganador = ?
            ''', (numero,))
            veces_ganador = cursor.fetchone()[0]

            resumen = f"Número {numero}:\n"
            resumen += f"🔹 Vendido {total_ventas[0]} veces\n"
            resumen += f"🔹 Total Apostado: C${total_ventas[1] or 0:,.0f}\n"
            resumen += f"🔹 Total Premio Potencial: C${total_ventas[2] or 0:,.0f}\n"
            resumen += f"🔹 Última venta: {total_ventas[3] or 'N/A'}\n"
            resumen += f"🔹 Ganador {veces_ganador} veces"

            self.resultado_busqueda.set(resumen)
        except Exception as e:
            messagebox.showerror("Error al buscar", f"Ocurrió un error: {e}")
        finally:
            conn.close()

            

    def actualizar_estado_ganadores_ventas(self):
        """
        Actualiza el Treeview en la pestaña de Ventas con el estado de los números ganadores
        para la fecha actual, resaltando los no ingresados.
        """
        for item in self.tree_ganadores_dia.get_children():
            self.tree_ganadores_dia.delete(item)
        
        fecha_actual = datetime.now().strftime('%Y-%m-%d')
        
        for sorteo in self.sorteo_options_all: # Iterar sobre todos los sorteos
            numero_ganador = consultar_numero_ganador_db(fecha_actual, sorteo)
            
            if numero_ganador:
                self.tree_ganadores_dia.insert("", tk.END, values=(sorteo, numero_ganador))
            else:
                # Si no hay número ganador, insertar "PENDIENTE" y aplicar el tag "no_ingresado"
                self.tree_ganadores_dia.insert("", tk.END, values=(sorteo, "PENDIENTE"), tags=('no_ingresado',))

    def mostrar_ventana_cambiar_clave(self):
        """Abre una nueva ventana para cambiar la clave de acceso (para la pestaña de configuracion)."""
        change_password_window = tk.Toplevel(self.root)
        change_password_window.title("Cambiar Clave de Acceso")
        
        # change_password_window.geometry("70x200") # Eliminar/Comentar para centrar
        change_password_window.resizable(False, False)
        change_password_window.grab_set()

        self.current_password_var = tk.StringVar()
        self.new_password_var = tk.StringVar()
        self.confirm_new_password_var = tk.StringVar()

        main_frame = ttk.Frame(change_password_window, padding="15 15 15 15")
        main_frame.pack(padx=20, pady=20, expand=True)

        ttk.Label(main_frame, text="Clave Actual:").grid(row=0, column=0, pady=5, sticky="w")
        current_entry = ttk.Entry(main_frame, show="*", textvariable=self.current_password_var)
        current_entry.grid(row=0, column=1, pady=5, sticky="ew")

        ttk.Label(main_frame, text="Nueva Clave:").grid(row=1, column=0, pady=5, sticky="w")
        new_entry = ttk.Entry(main_frame, show="*", textvariable=self.new_password_var)
        new_entry.grid(row=1, column=1, pady=5, sticky="ew")

        ttk.Label(main_frame, text="Confirmar Nueva Clave:").grid(row=2, column=0, pady=5, sticky="w")
        confirm_entry = ttk.Entry(main_frame, show="*", textvariable=self.confirm_new_password_var)
        confirm_entry.grid(row=2, column=1, pady=5, sticky="ew")

        ttk.Button(main_frame, text="Guardar Cambios", command=self.cambiar_clave, style='Accent.TButton').grid(row=3, column=0, columnspan=2, pady=10)

        main_frame.grid_columnconfigure(1, weight=1) # Permite que el campo de entrada se expanda

        # Centrar la ventana de cambio de clave
        change_password_window.update_idletasks()
        center_window(change_password_window)

        current_entry.focus_set()

        current_entry.bind("<Return>", lambda event: new_entry.focus_set())
        new_entry.bind("<Return>", lambda event: confirm_entry.focus_set())
        confirm_entry.bind("<Return>", lambda event: self.cambiar_clave())

    def cambiar_clave(self):
        clave_actual = self.current_password_var.get()
        nueva_clave = self.new_password_var.get()
        confirmar_nueva_clave = self.confirm_new_password_var.get()

        if not verificar_clave_db(clave_actual):
            messagebox.showerror("Error", "La clave actual es incorrecta.")
            return

        if nueva_clave == "":
            messagebox.showerror("Error", "La nueva clave no puede estar vacía.")
            return

        if nueva_clave != confirmar_nueva_clave:
            messagebox.showerror("Error", "La nueva clave y la confirmación no coinciden.")
            return

        exito, mensaje = actualizar_clave_db(nueva_clave)
        if exito:
            messagebox.showinfo("Éxito", mensaje)
            self.current_password_var.set("")
            self.new_password_var.set("")
            self.confirm_new_password_var.set("")
            try:
                # Obtener la ventana de cambio de clave y destruirla
                # Se puede hacer esto de forma más robusta si se almacena la referencia en la instancia
                # self.change_password_window.destroy()
                # Pero si solo hay una Toplevel abierta, esto funciona
                for widget in self.root.winfo_children():
                    if isinstance(widget, tk.Toplevel) and widget.title() == "Cambiar Clave de Acceso":
                        widget.destroy()
                        break
            except Exception: # Manejar si la ventana ya no existe
                pass
        else:
            messagebox.showerror("Error", mensaje)
            
    def guardar_premio_por_cordoba(self):
        """Guarda el nuevo valor del premio por cada C$1."""
        try:
            nuevo_valor_str = self.premio_por_cordoba_var.get()
            nuevo_valor = int(nuevo_valor_str)
            if nuevo_valor <= 0:
                messagebox.showerror("Error", "El valor del premio debe ser un número positivo.")
                return

            exito, mensaje = actualizar_premio_por_cordoba_db(nuevo_valor)
            if exito:
                messagebox.showinfo("Éxito", mensaje)
                self.actualizar_premio_calculado() # Recalcular el premio potencial en la pestaña de ventas
            else:
                messagebox.showerror("Error", mensaje)
        except ValueError:
            messagebox.showerror("Error de Entrada", "Por favor, ingrese un número entero válido para el premio.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error inesperado al guardar el premio: {e}")

    # Funciones para la pestaña de gestión de sorteos
    def registrar_ganador_gui(self):
        fecha_str = self.date_entry_registro.get_date().strftime('%Y-%m-%d')
        sorteo = self.sorteo_registro_var.get()
        numero_ganador_str = self.ganador_numero_var.get()

        try:
            numero_ganador = int(numero_ganador_str)
            if not (0 <= numero_ganador <= 99):
                raise ValueError("Número ganador inválido. Debe ser entre 00 y 99.")
            if not sorteo:
                raise ValueError("Debe seleccionar un sorteo.")
            
            exito, mensaje = registrar_numero_ganador_db(fecha_str, sorteo, numero_ganador)
            if exito:
                messagebox.showinfo("Registro Exitoso", mensaje)
                self.ganador_numero_var.set("")
                self.ganador_numero_entry.focus_set() # Volver a poner el foco para rápido ingreso
                self.actualizar_lista_ganadores()
                self.actualizar_estado_ganadores_ventas() # <--- IMPORTANTE: Actualizar también la pestaña de ventas
            else:
                messagebox.showerror("Error de Registro", mensaje)
        except ValueError as e:
            messagebox.showerror("Error de Entrada", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error inesperado: {e}")

    def consultar_ganador_gui(self):
        fecha_str = self.date_entry_consulta.get_date().strftime('%Y-%m-%d')
        sorteo = self.sorteo_consulta_var.get()

        if not sorteo:
            messagebox.showerror("Error", "Debe seleccionar un sorteo para consultar.")
            return

        numero_ganador = consultar_numero_ganador_db(fecha_str, sorteo)
        if numero_ganador:
            self.lbl_resultado_consulta.config(text=f"Número Ganador: {numero_ganador}", foreground="blue")
        else:
            self.lbl_resultado_consulta.config(text="Número Ganador: No registrado", foreground="red")

    def actualizar_lista_ganadores(self):
        for item in self.tree_ganadores.get_children():
            self.tree_ganadores.delete(item)
        
        ganadores = obtener_ultimos_ganadores_db(limite=10)
        for ganador in ganadores:
            self.tree_ganadores.insert("", tk.END, values=(ganador[0], ganador[1], ganador[2]))

    # Funciones para la pestaña de reportes
    def generar_reporte_gui(self):
        """Genera y muestra el reporte en la pestaña de reportes."""
        tipo_periodo = self.report_type.get() # Diario, Semanal, Mensual, Por Fecha
        tipo_datos = self.report_data_type_var.get() # Ventas o Ganadores

        # <<< CAMBIO INICIADO: Limpiar variables de fecha.
        fecha_inicio = None
        fecha_fin = None
        # <<< CAMBIO FINALIZADO
        mes_numero_seleccionado = None 
        anio_seleccionado = None
        sorteo_seleccionado = self.report_sorteo_var.get()

        # print(f"DEBUG: Generando reporte - Tipo de Datos: {tipo_datos}, Período: {tipo_periodo}, Sorteo: {sorteo_seleccionado}")

        # Obtener los parámetros de fecha/mes/año según el tipo de período
        # <<< CAMBIO INICIADO: Capturar el rango de fechas.
        if tipo_periodo == "por_fecha":
            try:
                fecha_inicio = self.date_entry_reporte_inicio.get_date().strftime('%Y-%m-%d')
                fecha_fin = self.date_entry_reporte_fin.get_date().strftime('%Y-%m-%d')
                if fecha_inicio > fecha_fin:
                    messagebox.showerror("Error de Fecha", "La fecha inicial no puede ser posterior a la fecha final.")
                    return
            except ValueError:
                messagebox.showerror("Error de Fecha", "Formato de fecha inválido.")
                self.report_text_area.config(state=tk.NORMAL)
                self.report_text_area.delete(1.0, tk.END)
                self.report_text_area.insert(tk.END, "Formato de fecha inválido. Seleccione una fecha válida.")
                self.report_text_area.config(state=tk.DISABLED)
                self.report_data = []
                self.report_type_data = None
                return
        # <<< CAMBIO FINALIZADO
        elif tipo_periodo == "mensual":
            mes_nombre_seleccionado = self.report_month_var.get()
            mes_numero_seleccionado = self.meses_map_reverse.get(mes_nombre_seleccionado) 
            anio_seleccionado = self.report_year_var.get()
            if not mes_numero_seleccionado or not anio_seleccionado:
                messagebox.showwarning("Advertencia", "Por favor, seleccione el mes y el año para el reporte mensual.")
                self.report_text_area.config(state=tk.NORMAL)
                self.report_text_area.delete(1.0, tk.END)
                self.report_text_area.insert(tk.END, "Por favor, seleccione un mes y año.")
                self.report_text_area.config(state=tk.DISABLED)
                self.report_data = []
                self.report_type_data = None
                return

        # Fetch data based on selected data type
        if tipo_datos == "Ventas":
            # <<< CAMBIO INICIADO: Pasar el rango de fechas a la función de la DB.
            self.report_data = obtener_ventas_para_reporte_db( 
                tipo_reporte=tipo_periodo,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                mes_numero_seleccionado=mes_numero_seleccionado,
                anio_seleccionado=anio_seleccionado,
                sorteo_seleccionado=sorteo_seleccionado
            )
            # <<< CAMBIO FINALIZADO
            self.report_type_data = "Ventas"
        elif tipo_datos == "Ganadores":
            # <<< CAMBIO INICIADO: Pasar el rango de fechas a la función de la DB.
            self.report_data = obtener_ganadores_para_reporte_db(
                tipo_reporte=tipo_periodo,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                mes_numero_seleccionado=mes_numero_seleccionado,
                anio_seleccionado=anio_seleccionado,
                sorteo_seleccionado=sorteo_seleccionado
            )
            # <<< CAMBIO FINALIZADO
            self.report_type_data = "Ganadores"

        self.report_text_area.config(state=tk.NORMAL)
        self.report_text_area.delete(1.0, tk.END)

        # <<< CAMBIO INICIADO: Actualizar el mapa de títulos para el rango de fechas.
        titulo_map = {
            "diario": "Diario",
            "semanal": "Semanal",
            "mensual": f"Mensual de {self.report_month_var.get()}/{self.report_year_var.get()}",
            "por_fecha": f"para el rango de {fecha_inicio} a {fecha_fin}"
        }
        # <<< CAMBIO FINALIZADO
        
        titulo_base = f"Reporte {tipo_datos} {titulo_map.get(tipo_periodo, '')}"

        if sorteo_seleccionado and sorteo_seleccionado != "Todos":
            titulo_base += f" (Sorteo: {sorteo_seleccionado})"

        self.report_content = "" # Reset report_content

        if not self.report_data:
            self.report_content = f"No hay {tipo_datos.lower()} registradas para el {titulo_base} en el período/filtros seleccionados."
            self.report_text_area.insert(tk.END, self.report_content)
        else:
            self.report_content += f"--- {titulo_base} ---\n\n"

            if tipo_datos == "Ventas":
                total_apostado_general = 0
                total_premio_potencial_general = 0
                
                # Columnas y sus anchos para el reporte de texto (ajustado para la nueva columna "Última Modificación")
                col_widths_text = {
                    "Numero": 8,     
                    "Sorteo": 10,    
                    "Apuesta Total": 15, 
                    "Premio Total": 15,  
                    "Última Modificación": 20 # Nueva columna para la fecha_hora
                }
                self.report_content += "{:<{num_w}} {:<{sort_w}} {:<{ap_w}} {:<{pr_w}} {:<{ult_mod_w}}\n".format(
                    "Número", "Sorteo", "Apuesta Total", "Premio Total", "Última Mod.", 
                    num_w=col_widths_text["Numero"],
                    sort_w=col_widths_text["Sorteo"],
                    ap_w=col_widths_text["Apuesta Total"], 
                    pr_w=col_widths_text["Premio Total"],  
                    ult_mod_w=col_widths_text["Última Modificación"]
                )
                self.report_content += "-" * (sum(col_widths_text.values()) + 4) + "\n"

                for venta in self.report_data: 
                    # Datos de la consulta agrupada: numero_loteria, SUM(apuesta), SUM(premio_potencial), venta_fecha_solo_dia, sorteo_hora, MAX(fecha_hora)
                    numero, apuesta_total, premio_total, _, sorteo_hora, ultima_modificacion_hora_venta = venta 
                    
                    apuesta_formatted = f"{apuesta_total:,.0f}" 
                    premio_formatted = f"{premio_total:,.0f}"

                    self.report_content += "{:<{num_w}} {:<{sort_w}} {:<{ap_val_w}} {:<{pr_val_w}} {:<{ult_mod_val_w}}\n".format(
                        numero, sorteo_hora, apuesta_formatted, premio_formatted, ultima_modificacion_hora_venta, 
                        num_w=col_widths_text["Numero"],
                        sort_w=col_widths_text["Sorteo"],
                        ap_val_w=col_widths_text["Apuesta Total"], 
                        pr_val_w=col_widths_text["Premio Total"], 
                        ult_mod_val_w=col_widths_text["Última Modificación"]
                    )
                    total_apostado_general += apuesta_total 
                    total_premio_potencial_general += premio_total
                
                self.report_content += "-" * (sum(col_widths_text.values()) + 4) + "\n"
                self.report_content += f"\nGran Total Apostado: C${total_apostado_general:,.0f}\n" 
                self.report_content += f"Gran Total Premio Potencial: C${total_premio_potencial_general:,.0f}\n"

            elif tipo_datos == "Ganadores":
                col_widths_text = {
                    "Fecha Sorteo": 15,
                    "Hora Sorteo": 12,
                    "Número Ganador": 15,
                    "Total Apostado": 17,
                    "Total Premios": 17
                }

                self.report_content += "{:<{f_w}} {:<{h_w}} {:<{n_w}} {:>{a_w}} {:>{p_w}}\n".format(
                    "Fecha Sorteo", "Hora Sorteo", "Número Ganador", "Total Apostado", "Total Premios",
                    f_w=col_widths_text["Fecha Sorteo"],
                    h_w=col_widths_text["Hora Sorteo"],
                    n_w=col_widths_text["Número Ganador"],
                    a_w=col_widths_text["Total Apostado"],
                    p_w=col_widths_text["Total Premios"]
                )
                self.report_content += "-" * (sum(col_widths_text.values()) + 5) + "\n"

                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()

                for ganador in self.report_data:
                    fecha_sorteo, hora_sorteo, numero_ganador, total_apostado, premio_pagado = ganador

                    cursor.execute('''
                        SELECT SUM(apuesta), SUM(premio_potencial)
                        FROM ventas
                        WHERE numero_loteria = ? AND venta_fecha_solo_dia = ? AND sorteo_hora = ?
                    ''', (numero_ganador, fecha_sorteo, hora_sorteo))

                    suma = cursor.fetchone()
                    total_apostado = suma[0] if suma and suma[0] else 0
                    total_premio = suma[1] if suma and suma[1] else 0

                    self.report_content += "{:<{f_w}} {:<{h_w}} {:<{n_w}} {:>{a_w}} {:>{p_w}}\n".format(
                        fecha_sorteo, hora_sorteo, numero_ganador,
                        f"C${total_apostado:,.0f}", f"C${premio_pagado:,.0f}",
                        f_w=col_widths_text["Fecha Sorteo"],
                        h_w=col_widths_text["Hora Sorteo"],
                        n_w=col_widths_text["Número Ganador"],
                        a_w=col_widths_text["Total Apostado"],
                        p_w=col_widths_text["Total Premios"]
                    )


                conn.close()
                
            self.report_text_area.delete(1.0, tk.END)
            self.report_text_area.insert(tk.END, self.report_content)
        self.report_text_area.config(state=tk.DISABLED)

    def exportar_reporte_a_pdf(self):
        """Exporta el contenido actual del reporte a un archivo PDF en la subcarpeta 'Reportes',
        con nombre de archivo basado en la fecha y hora, y lo abre automáticamente,
        con formato de tabla."""
        self.generar_reporte_gui()
        if not hasattr(self, 'report_data') or not self.report_data:
            messagebox.showwarning("Exportar a PDF", "No hay contenido de reporte para exportar.")
            return

        try:
            reportes_dir = os.path.join(os.getcwd(), "Reportes")
            os.makedirs(reportes_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Ajustar el nombre del archivo según el tipo de reporte
            if self.report_type_data == "Ventas":
                file_name = f"Reporte_Ventas_{timestamp}.pdf"
            elif self.report_type_data == "Ganadores":
                file_name = f"Reporte_Ganadores_{timestamp}.pdf"
            else:
                file_name = f"Reporte_General_{timestamp}.pdf"

            file_path = os.path.join(reportes_dir, file_name)

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)

            # Extraer el título del report_content para usarlo en el PDF
            title_text = "Reporte de Ventas" # Default
            match = re.search(r"--- (.*?) ---", self.report_content.split('\n')[0])
            if match:
                title_text = match.group(1).strip()
            
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, title_text, 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C') 
            pdf.ln(5)
            pdf.set_font("Arial", size=10)
            
            line_height_pdf = 7

            if self.report_type_data == "Ventas":
                # Anchos para el PDF (ajustados para la nueva columna "Última Modificación")
                col_widths_pdf = {
                    "Numero": 20,
                    "Sorteo": 20,
                    "Apuesta Total": 40,
                    "Premio Total": 35,
                    "Última Modificación": 65
                }

                # Encabezado de la tabla para Ventas
                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(220, 220, 220)
                pdf.cell(col_widths_pdf["Numero"], line_height_pdf, "Número", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Sorteo"], line_height_pdf, "Sorteo", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Apuesta Total"], line_height_pdf, "Apuesta Total (C$)", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True) 
                pdf.cell(col_widths_pdf["Premio Total"], line_height_pdf, "Premio Total (C$)", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True) 
                pdf.cell(col_widths_pdf["Última Modificación"], line_height_pdf, "Última Modificación", 1, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C', fill=True)
                pdf.set_font("Arial", size=10)
                pdf.set_fill_color(255, 255, 255)

                total_apostado_general = 0
                total_premio_potencial_general = 0

                for venta in self.report_data: # ventas agrupadas
                    # numero_loteria, SUM(apuesta), SUM(premio_potencial), venta_fecha_solo_dia, sorteo_hora, MAX(fecha_hora)
                    numero, apuesta_total, premio_total, _, sorteo_hora, ultima_modificacion_hora_venta = venta
                    apuesta_formatted = f"{apuesta_total:,.0f}" 
                    premio_formatted = f"{premio_total:,.0f}"

                    pdf.cell(col_widths_pdf["Numero"], line_height_pdf, str(numero), 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C')
                    pdf.cell(col_widths_pdf["Sorteo"], line_height_pdf, sorteo_hora, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C')
                    pdf.cell(col_widths_pdf["Apuesta Total"], line_height_pdf, apuesta_formatted, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='L') 
                    pdf.cell(col_widths_pdf["Premio Total"], line_height_pdf, premio_formatted, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='L') 
                    pdf.cell(col_widths_pdf["Última Modificación"], line_height_pdf, ultima_modificacion_hora_venta, 1, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C')
                    
                    total_apostado_general += apuesta_total 
                    total_premio_potencial_general += premio_total

                pdf.ln(5)
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 7, f"Gran Total Apostado: C${total_apostado_general:,.0f}", 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='L')
                pdf.cell(0, 7, f"Gran Total Premio Potencial: C${total_premio_potencial_general:,.0f}", 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='L')
            
            elif self.report_type_data == "Ganadores":
                col_widths_pdf = {
                    "Fecha Sorteo": 30,
                    "Hora Sorteo": 20,
                    "Número Ganador": 30,
                    "Total Apostado": 30,
                    "Premio Pagado": 30
                }

                # Encabezados de tabla
                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(220, 220, 220)
                pdf.cell(col_widths_pdf["Fecha Sorteo"], line_height_pdf, "Fecha", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Hora Sorteo"], line_height_pdf, "Sorteo", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Número Ganador"], line_height_pdf, "Ganador", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Total Apostado"], line_height_pdf, "Apostado (C$)", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Premio Pagado"], line_height_pdf, "Pagado (C$)", 1, 1, 'C', True)

                pdf.set_font("Arial", size=10)
                pdf.set_fill_color(255, 255, 255)

                for fila in self.report_data:
                    # Asegúrate de que tu self.report_data contiene estos cinco valores por fila
                    if len(fila) < 5:
                        messagebox.showwarning("Error de Datos", "El reporte no tiene las columnas completas. Vuelve a generarlo antes de exportar.")
                        return
                    fecha_sorteo, hora_sorteo, numero_ganador, total_apostado, total_pagado = fila
                    pdf.cell(col_widths_pdf["Fecha Sorteo"], line_height_pdf, fecha_sorteo, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Hora Sorteo"], line_height_pdf, hora_sorteo, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Número Ganador"], line_height_pdf, numero_ganador, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Total Apostado"], line_height_pdf, f"{total_apostado:,.0f}", 1, 0, 'R')
                    pdf.cell(col_widths_pdf["Premio Pagado"], line_height_pdf, f"{total_pagado:,.0f}", 1, 1, 'R')



            pdf.output(file_path)
            temp_pdf_files.append(file_path)

            if sys.platform == "win32":
                try:
                    os.startfile(file_path)
                except OSError:
                    messagebox.showwarning("Advertencia", f"No se pudo abrir el PDF automáticamente. Por favor, ábralo manualmente desde:\n{file_path}")
            elif sys.platform == "darwin": 
                subprocess.Popen(["open", "open", file_path])
            else: 
                subprocess.Popen(["xdg-open", file_path])

            messagebox.showinfo("Exportar a PDF", f"Reporte guardado y abierto exitosamente en:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error al Exportar", f"Ocurrió un error al exportar el PDF: {e}")
            # print(f"ERROR: Exception during PDF export: {e}") 

    def imprimir_reporte_gui(self):
        """Genera un PDF temporal y lo abre para imprimir."""
        if not hasattr(self, 'report_data') or not self.report_data:
            messagebox.showwarning("Imprimir Reporte", "No hay contenido de reporte para imprimir.")
            return

        try:
            temp_pdf_dir = "temp_pdfs"
            os.makedirs(temp_pdf_dir, exist_ok=True)
            temp_pdf_path = os.path.join(temp_pdf_dir, f"reporte_temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)

            # Extraer el título del report_content para usarlo en el PDF
            title_text = "Reporte de Ventas" # Default
            match = re.search(r"--- (.*?) ---", self.report_content.split('\n')[0])
            if match:
                title_text = match.group(1).strip()
            
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, title_text, 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C')
            pdf.ln(5)
            pdf.set_font("Arial", size=10)

            line_height_pdf = 7

            if self.report_type_data == "Ventas":
                # Anchos para el PDF (ajustados para la nueva columna "Última Modificación")
                col_widths_pdf = {
                    "Numero": 20,
                    "Sorteo": 20,
                    "Apuesta Total": 40,
                    "Premio Total": 35,
                    "Última Modificación": 65
                }
                
                # Encabezado de la tabla para Ventas
                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(220, 220, 220)
                pdf.cell(col_widths_pdf["Numero"], line_height_pdf, "Número", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Sorteo"], line_height_pdf, "Sorteo", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Apuesta Total"], line_height_pdf, "Apuesta Total (C$)", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Premio Total"], line_height_pdf, "Premio Total (C$)", 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C', fill=True)
                pdf.cell(col_widths_pdf["Última Modificación"], line_height_pdf, "Última Modificación", 1, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C', fill=True)
                pdf.set_font("Arial", size=10)
                pdf.set_fill_color(255, 255, 255)

                total_apostado_general = 0
                total_premio_potencial_general = 0

                for venta in self.report_data:
                    numero, apuesta_total, premio_total, _, sorteo_hora, ultima_modificacion_hora_venta = venta
                    apuesta_formatted = f"{apuesta_total:,.0f}" 
                    premio_formatted = f"{premio_total:,.0f}"

                    pdf.cell(col_widths_pdf["Numero"], line_height_pdf, str(numero), 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C')
                    pdf.cell(col_widths_pdf["Sorteo"], line_height_pdf, sorteo_hora, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='C')
                    pdf.cell(col_widths_pdf["Apuesta Total"], line_height_pdf, apuesta_formatted, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='L')
                    pdf.cell(col_widths_pdf["Premio Total"], line_height_pdf, premio_formatted, 1, new_x=enums.XPos.RIGHT, new_y=enums.YPos.TOP, align='L')
                    pdf.cell(col_widths_pdf["Última Modificación"], line_height_pdf, ultima_modificacion_hora_venta, 1, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='C')

                    total_apostado_general += apuesta_total
                    total_premio_potencial_general += premio_total

                pdf.ln(5)
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 7, f"Gran Total Apostado: C${total_apostado_general:,.0f}", 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='L')
                pdf.cell(0, 7, f"Gran Total Premio Potencial: C${total_premio_potencial_general:,.0f}", 0, new_x=enums.XPos.LMARGIN, new_y=enums.YPos.NEXT, align='L')
            
            elif self.report_type_data == "Ganadores":
                col_widths_pdf = {
                    "Fecha Sorteo": 30,
                    "Hora Sorteo": 20,
                    "Número Ganador": 30,
                    "Apostado": 30,
                    "Pagado": 30
                }

                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(220, 220, 220)
                pdf.cell(col_widths_pdf["Fecha Sorteo"], line_height_pdf, "Fecha", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Hora Sorteo"], line_height_pdf, "Sorteo", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Número Ganador"], line_height_pdf, "Ganador", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Apostado"], line_height_pdf, "Apostado (C$)", 1, 0, 'C', True)
                pdf.cell(col_widths_pdf["Pagado"], line_height_pdf, "Pagado (C$)", 1, 1, 'C', True)

                pdf.set_font("Arial", size=10)
                pdf.set_fill_color(255, 255, 255)

                for fila in self.report_data:
                    fecha_sorteo, hora_sorteo, numero_ganador, total_apostado, premio_pagado = fila
                    pdf.cell(col_widths_pdf["Fecha Sorteo"], line_height_pdf, fecha_sorteo, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Hora Sorteo"], line_height_pdf, hora_sorteo, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Número Ganador"], line_height_pdf, numero_ganador, 1, 0, 'C')
                    pdf.cell(col_widths_pdf["Apostado"], line_height_pdf, f"{total_apostado:,.0f}", 1, 0, 'R')
                    pdf.cell(col_widths_pdf["Pagado"], line_height_pdf, f"{premio_pagado:,.0f}", 1, 1, 'R')


            pdf.output(temp_pdf_path)
            temp_pdf_files.append(temp_pdf_path)

            if sys.platform == "win32":
                os.startfile(temp_pdf_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", temp_pdf_path])
            else:
                subprocess.Popen(["xdg-open", temp_pdf_path])

            messagebox.showinfo("Imprimir Reporte", f"El reporte PDF ha sido generado y se intentará abrir para imprimir:\n{temp_pdf_path}\n\nSi no se abre, por favor ábralo manualmente y use la función de impresión.")

        except FileNotFoundError:
            messagebox.showerror("Error de Impresión", "No se encontró un programa para abrir PDF. Asegúrese de tener un lector de PDF instalado.")
        except Exception as e:
            messagebox.showerror("Error al Imprimir", f"Ocurrió un error al generar/abrir el PDF para impresión: {e}")
            # print(f"ERROR: Exception during PDF print: {e}") 

from collections import Counter

def obtener_top_numeros_mas_vendidos_hoy(limit=5):
    """Devuelve los N números más vendidos hoy con el total de apuesta."""
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
    SELECT numero_loteria, SUM(apuesta) as total
    FROM ventas
    WHERE venta_fecha_solo_dia = ?
    GROUP BY numero_loteria
    ORDER BY total DESC
    LIMIT ?
    ''', (fecha_actual, limit))

    resultados = cursor.fetchall()
    conn.close()
    return resultados  # Lista de tuplas (numero, total_apuesta)

def obtener_total_apostado_por_sorteo_semana():
    """Devuelve una lista con el total apostado en la semana por sorteo."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    hoy = datetime.now()
    lunes = hoy - timedelta(days=hoy.weekday())  # lunes de esta semana
    fecha_inicio = lunes.strftime('%Y-%m-%d')

    cursor.execute('''
        SELECT sorteo_hora, SUM(apuesta) as total_apuesta
        FROM ventas
        WHERE venta_fecha_solo_dia >= ?
        GROUP BY sorteo_hora
        ORDER BY sorteo_hora
    ''', (fecha_inicio,))
    
    resultados = cursor.fetchall()
    conn.close()
    return resultados  # Ejemplo: [('03 PM', 450), ('06 PM', 620), ...]

def obtener_apuestas_vs_premios_semana():
    """
    Devuelve una lista con cada sorteo y su total apostado vs total pagado en premios,
    desde el lunes hasta hoy.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    hoy = datetime.now()
    lunes = hoy - timedelta(days=hoy.weekday())
    fecha_inicio = lunes.strftime('%Y-%m-%d')

    # Total apostado por sorteo
    cursor.execute('''
        SELECT sorteo_hora, SUM(apuesta) FROM ventas
        WHERE venta_fecha_solo_dia >= ?
        GROUP BY sorteo_hora
    ''', (fecha_inicio,))
    apuestas = dict(cursor.fetchall())

    # Total premios entregados por sorteo (si hubo coincidencia con número ganador)
    cursor.execute('''
        SELECT v.sorteo_hora, SUM(v.premio_potencial)
        FROM ventas v
        JOIN resultados_sorteo r
            ON v.venta_fecha_solo_dia = r.fecha_sorteo
            AND v.sorteo_hora = r.hora_sorteo
            AND v.numero_loteria = r.numero_ganador
        WHERE v.venta_fecha_solo_dia >= ?
        GROUP BY v.sorteo_hora
    ''', (fecha_inicio,))
    premios = dict(cursor.fetchall())

    conn.close()

    sorteos = ['11 AM', '03 PM', '06 PM', '09 PM']
    resultado = []
    for sorteo in sorteos:
        total_ap = apuestas.get(sorteo, 0)
        total_pr = premios.get(sorteo, 0)
        resultado.append((sorteo, total_ap, total_pr))

    return resultado


def eliminar_ultima_venta_valida_db():
    """Elimina el último registro real de venta basado en la fecha y hora más reciente."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id FROM ventas
            ORDER BY fecha_hora DESC
            LIMIT 1
        ''')
        ultima = cursor.fetchone()
        if ultima:
            cursor.execute('DELETE FROM ventas WHERE id = ?', (ultima[0],))
            conn.commit()
            return True, "✅ Última venta eliminada correctamente."
        else:
            return False, "❌ No hay ventas para eliminar."
    except sqlite3.Error as e:
        return False, f"❌ Error al eliminar la última venta: {e}"
    finally:
        conn.close()

def crear_respaldo_codigo_txt():
    import os
    import sys

    try:
        # Detecta la ruta del archivo fuente principal
        if hasattr(sys, 'argv') and sys.argv[0]:
            ruta_py = os.path.abspath(sys.argv[0])
        else:
            print("❌ No se pudo determinar la ruta del archivo ejecutado.")
            return

        nombre_sin_ext = os.path.splitext(os.path.basename(ruta_py))[0]
        ruta_txt = os.path.join(os.path.dirname(ruta_py), f"{nombre_sin_ext}_respaldo.txt")

        with open(ruta_py, 'r', encoding='utf-8') as f_origen, open(ruta_txt, 'w', encoding='utf-8') as f_destino:
            f_destino.write(f_origen.read())

        print(f"✅ Respaldo creado: {ruta_txt}")
    except Exception as e:
        print(f"❌ Error al crear respaldo: {e}")

# --- Punto de Entrada de la Aplicación ---
if __name__ == "__main__":
    crear_tabla()
    crear_respaldo_codigo_txt()  # Siempre genera/reescribe el respaldo
    root = tk.Tk()
    root.withdraw() # Oculta la ventana principal hasta que el login sea exitoso

    # INICIO TEMPORAL: BYPASS DE LOGIN
    # Comenta estas líneas para siempre iniciar la aplicación directamente y
    # poder acceder a la pestaña de configuración para manejar la clave.
    # if existe_clave_acceso_configurada():
    #     login_window = LoginWindow(root)
    #     root.wait_window(login_window)

    #     if not login_window.login_successful:
    #         root.destroy()
    #         sys.exit(0)
    # FIN TEMPORAL: BYPASS DE LOGIN
    
    app = AppLoteria(root)
    root.deiconify() # Muestra la ventana principal
    root.mainloop()