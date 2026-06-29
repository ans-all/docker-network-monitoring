from flask import Flask, render_template, request, redirect, jsonify, flash, session # import Flask dari library falsk
import pymysql
import os
import socket
import time
from apscheduler.schedulers.background import BackgroundScheduler
import requests


app = Flask(__name__) # buat aplikasi Flask
app.secret_key = 'kunci_rahasia_monitoring'

def get_db_connection():
    connection = pymysql.connect(
        host = os.environ.get('DB_HOST'),
        user = os.environ.get('DB_USER'),
        password = os.environ.get('DB_PASSWORD'),
        database = os.environ.get('DB_NAME'),
        cursorclass = pymysql.cursors.DictCursor
    )
    return connection


# IMPLEMENTASI BOT TEGLEGRAM
def send_notif(pesan):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.get(url, params={
        'chat_id': chat_id,
        'text': pesan
    })

def monitor_all_host():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM hosts")
            d_hosts = cursor.fetchall()
            for hosts in d_hosts:
                f_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((hosts['ip_address'], hosts['port']))
                sock.close()
                l_time = time.time()

                time_result = (l_time - f_time) * 1000
                if result == 0:
                    status = "online"
                    latency = f"{time_result:.1f} ms"
                else:
                    status = "offline"
                    latency = "N/A"
                
                with connection.cursor() as cursor2:
                    sql="SELECT status FROM logs WHERE host_id = %s ORDER BY create_at DESC LIMIT 1"
                    cursor2.execute(sql, (hosts['id'],))
                    l_log=cursor2.fetchone()
                    l_status=l_log['status'] if l_log else None

                with connection.cursor() as cursor1:
                    sql = "INSERT INTO logs (host_id, status, latency) VALUES (%s, %s, %s)"
                    cursor1.execute(sql,(hosts['id'], status, latency))

                if status=='offline' and l_status!='offline':
                    send_notif(f"{hosts['hostname']} OFFLINE")
                elif status=='online' and l_status=='offline':
                    send_notif(f"{hosts['hostname']} kembali ONLINE")

            connection.commit()
        connection.close()
    except Exception as e:
        print(f"[monitor] Error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(monitor_all_host, 'interval', seconds=1)




@app.route('/')
def index():
    connection = get_db_connection()  # BUKA KONEKSI
    with connection.cursor() as cursor: # buat cursor
        cursor.execute("SELECT * FROM hosts") # jalankan sql
        d_hosts = cursor.fetchall() #ambil semua hasil query
         
    with connection.cursor() as cursor1:
        # mendapatkan total hsots dengan count()
        cursor1.execute("SELECT COUNT(*) AS total_hosts FROM hosts")
        total_hosts = cursor1.fetchone()['total_hosts']

        sql="SELECT  host_id, status " \
            "FROM logs " \
            "WHERE create_at IN (" \
                "SELECT MAX(create_at) " \
                "FROM logs " \
                "GROUP BY host_id)"
        cursor1.execute(sql)
        latest_logs = cursor1.fetchall()

        online = sum(1 for log in latest_logs if log['status']=='online')
        offline = 0
        for log in latest_logs:
            if log['status'] == 'offline':
                offline +=1
        
        sql="SELECT COUNT(*) AS total from logs"
        cursor1.execute(sql)
        total_logs = cursor1.fetchone()['total']

        sql="SELECT COUNT(*) AS online_count FROM logs WHERE status = 'online'"
        cursor1.execute(sql)
        online_logs = cursor1.fetchone()['online_count']

        uptime = round((online_logs / total_logs * 100), 1) if total_logs > 0 else 0

        connection.close() # tutup koneksi

    return render_template('index.html', hosts=d_hosts, total=total_hosts, online=online, offline=offline, uptime=uptime) #rander dangan mengirim data di variabel d_hosts


@app.route('/add', methods=['POST'])
def add_host():
    hostname = request.form['hostname']
    ip_address =  request.form['ip_address']
    port = request.form['port']
    description = request.form['description']

    if port == "":
        port = 80

    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = "INSERT INTO hosts (hostname, ip_address, port, description) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (hostname, ip_address, port, description))
        connection.commit()
    connection.close()
    return redirect('/')
    
@app.route('/delete/<int:host_id>')
def delete_host(host_id):
    connection =  get_db_connection()
    with connection.cursor() as cursor:
        sql="SELECT COUNT(*) AS jumlah_log FROM logs WHERE host_id=%s"
        cursor.execute(sql, (host_id,))
        jumlah_log = cursor.fetchone()['jumlah_log']

        if jumlah_log > 0:
            flash(f"Host tidak bisa di hapus! Host ini masih memiliki {jumlah_log} log tersimpan", "danger")
            connection.close()
            return redirect('/')
        
        sql = "DELETE FROM hosts WHERE id = %s"
        cursor.execute(sql,(host_id,))
        connection.commit()
    connection.close()
    return redirect('/')

@app.route('/edit/<int:host_id>')
def edit_host(host_id):
    connection  = get_db_connection()
    with connection.cursor() as cursor:
        sql = "SELECT * FROM hosts WHERE id = %s"
        cursor.execute(sql, (host_id,))
        d_id_hosts = cursor.fetchone() #ambil satu data saja yang di kirim
    connection.close()
    return render_template('edit.html', host=d_id_hosts)


@app.route('/update/<int:host_id>', methods=['POST'])
def update_host(host_id):
    hostname = request.form['hostname']
    ip_address = request.form['ip_address']
    port = request.form['port']
    description = request.form['description']

    if port == "":
        port = 80

    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = "UPDATE hosts SET hostname = %s, ip_address = %s, port = %s, description = %s WHERE id = %s"
        cursor.execute(sql, (hostname, ip_address, port, description, host_id))
        connection.commit()
    connection.close()
    return redirect('/')

@app.route('/check/<int:host_id>')
def check_host(host_id):
    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = "SELECT * FROM hosts WHERE id = %s"
        cursor.execute(sql, (host_id,))
        d_hosts = cursor.fetchone()
    
    # tcp shoket chekc
    f_time = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((d_hosts['ip_address'], d_hosts['port']))
    sock.close()
    l_time = time.time()
    
    time_result = (l_time - f_time) * 1000
    if result == 0:
        status = "online"
        latency = f"{time_result:.1f} ms"
    else:
        status = "offline"
        latency = "N/A"

    with connection.cursor() as cursor:
        sql = "INSERT INTO logs (host_id, status, latency) VALUES (%s, %s, %s)"
        cursor.execute(sql, (host_id, status, latency ))
        connection.commit()
        
    connection.close()
    return render_template('check.html', host=d_hosts, status=status, latency=latency)
    


@app.route('/logs')
def logs():
    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = """
            SELECT logs.id, logs.host_id, logs.status, logs.latency, logs.create_at, hosts.hostname
            FROM logs
            JOIN hosts ON logs.host_id = hosts.id
        """
        conditions = []
        params = []
        status_filter = request.args.get('status')
        host_filter = request.args.get('host_id')
        if status_filter:
            conditions.append("logs.status = %s")
            params.append(status_filter)
        if host_filter:
            conditions.append("logs.host_id = %s")
            params.append(host_filter)
        
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY logs.create_at DESC"
        cursor.execute(sql, params)
        d_logs = cursor.fetchall()
    connection.close()
    return render_template('logs.html', logs=d_logs)

@app.route('/delete/log/<int:host_id>')
def delete_log(host_id):
    connectioon = get_db_connection()
    with connectioon.cursor() as cursor:
        sql="DELETE FROM logs WHERE host_id=%s"
        cursor.execute(sql, (host_id,))
        connectioon.commit()
    connectioon.close()
    return redirect('/logs')

@app.route('/api/uptime') # JSON data uptime per host
def uptime():
    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql="SELECT hosts.hostname, " \
            "COUNT(*) AS total, " \
            "SUM(CASE WHEN logs.status = 'online' THEN 1 ELSE 0 END) AS online_count " \
            "FROM logs " \
            "JOIN hosts ON logs.host_id = hosts.id " \
            "GROUP BY hosts.hostname"
        cursor.execute(sql)
        d_hosts=cursor.fetchall()
        labels=[]
        data=[]
        for row in d_hosts:
            labels.append(row['hostname'])
            uptime = round(row['online_count'] / row['total'] * 100, 1)
            data.append(uptime)
        connection.close()
    return jsonify({"labels": labels, "data": data})
    

@app.route('/api/latency') # JSON data latency rata-rata per host
def latency():
    db=get_db_connection()
    with db.cursor() as c:
        sql="SELECT hosts.hostname, " \
                "AVG(CAST(REPLACE(logs.latency, ' ms', '') AS DECIMAL(10,2))) AS avg_latency " \
            "FROM logs " \
            "JOIN hosts ON logs.host_id = hosts.id " \
            "WHERE logs.status = 'online' " \
            "GROUP BY hosts.hostname"
        c.execute(sql)
        d_hosts = c.fetchall()
        data=[]
        labels=[]
        for row in d_hosts:
            labels.append(row['hostname'])
            data.append(row['avg_latency'])
    db.close()
    return jsonify({"labels": labels, "data": data})


@app.route('/charts') #render charts.html (berisi Chars.js)
def charts():
    return render_template('charts.html')


if  __name__ == '__main__': #Jalankan aplikasi flask
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

