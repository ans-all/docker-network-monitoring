from flask import Flask, render_template, request, redirect # import Flask dari library falsk
import pymysql
import os
import socket
import time
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__) # buat aplikasi Flask

def get_db_connection():
    connection = pymysql.connect(
        host = os.environ.get('DB_HOST'),
        user = os.environ.get('DB_USER'),
        password = os.environ.get('DB_PASSWORD'),
        database = os.environ.get('DB_NAME'),
        cursorclass = pymysql.cursors.DictCursor
    )
    return connection

def monitor_all_host():
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
                
            with connection.cursor() as cursor1:
                sql = "INSERT INTO logs (host_id, status, latency) VALUES (%s, %s, %s)"
                cursor1.execute(sql,(hosts['id'], status, latency))
        connection.commit()
    connection.close()

scheduler = BackgroundScheduler()
scheduler.add_job(monitor_all_host, 'interval', minutes=0.1)


@app.route('/')
def index():
    connection = get_db_connection()  # BUKA KONEKSI
    with connection.cursor() as cursor: # buat cursor
        cursor.execute("SELECT * FROM hosts") # jalankan sql
        d_hosts = cursor.fetchall() #ambil semua hasil query
    connection.close() # tutup koneksi
    return render_template('index.html', hosts=d_hosts) #rander dangan mengirim data di variabel d_hosts


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
            SELECT logs.id, logs.status, logs.latency, logs.create_at, hosts.hostname
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




if  __name__ == '__main__': #Jalankan aplikasi flask
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True)

