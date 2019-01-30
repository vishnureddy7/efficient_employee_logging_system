import threading
import pymysql
from queue import Queue
from datetime import datetime
import serial
import random
import schedule
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from time import sleep
from datetime import timedelta


db=None

#get the data from the scanner
def get_data(out_queue):
    try:
        #start the serial reader at COM3 port
        serial_reader = serial.Serial('COM3',9600);
    except Exception as e:
        print("Error occured while trying to connect the scanner.\n");
        print(e);
        return;
    while(True):
        try:
            #read one line from scanner
            incoming=serial_reader.readline().decode()[:-2]
            #put the received data onto the queue
            out_queue.put(incoming);
            print("recieved employee id %s\n"%(incoming));
        except Exception as e:
            print("Error occured while waiting for incoming data from the scanner.\n");
            print(e);
            break;
    #close the connection to the scanner
    serial_reader.close();
    out_queue.put("EOF");
    out_queue.task_done();
    print("serial reader seems to be disconnected..\n");

#make db connection and update db
def getdb():
    global db
    #database server details
    db_host = "localhost";
    db_user = "root";
    db_password = "";
    db_database = "employee_logging_system";
    try:
        #connect to database using the credentials
        db = pymysql.connect(db_host, db_user, db_password, db_database);
    except Exception as e:
        print("Error occured while connecting to database.\n");
        print(e);
        return -1;

#insert the received data into database
def data_process(in_queue):
    global db
    if(db is None):
        if(getdb() == -1):
            return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    while(True):
        #receive the data from the queue sent by get data
        emp_id = in_queue.get();
        if(emp_id == "EOF"):
            break;
        #check if the employee id is valid
        if(len(emp_id) < 12 or emp_id.find(' ')!=-1):
            print("invalid employee id %s\n" %(emp_id));
            continue;
        #get the current date and time
        cur_date = datetime.now().date().isoformat();
        cur_time = datetime.now().time().isoformat()[:8];
        #generate the logid --> emp_id + date
        log_id = emp_id + cur_date.replace('-','');
        in_or_out = get_in_or_out(db_cursor,log_id,emp_id,cur_date,cur_time);
        #insert the log date into the table
        db_cursor.execute("INSERT INTO log_data VALUES('%s','%s','%s','%s',%d);" % (log_id,cur_date,cur_time,emp_id,in_or_out));
        #commit the query
        db.commit();
        print("successfully processed %s \n" % (emp_id));
    #close the connection to the database
    in_queue.task_done();
    db_cursor.close();
    db.close();
    print("data_process is completed");

#based on scan identify whether comming in or going out
def get_in_or_out(db_cursor,log_id,emp_id,cur_date,cur_time):
    #execute the query
    no_of_results = db_cursor.execute("SELECT * FROM log_data WHERE log_id = '%s' ORDER BY time DESC;"%(log_id));
    #if it is the first time the user logging in a day, then it is login
    if(no_of_results == 0):
        return 0;
    results = db_cursor.fetchall();
    #if last is login then logout or login
    return 1-results[0][-1];


#time based activities
def time_based_activity():
    schedule.every().day.at("08:05:10").do(cabs_at_730);
    schedule.every().day.at("08:05:40").do(cabs_at_930);
    schedule.every().day.at("08:06:00").do(update_total_logs);
    schedule.every().day.at("08:06:30").do(send_log_updatemails);
    while True:
        schedule.run_pending()
        sleep(1)

#send notification of cabs at 7:30
def cabs_at_730():
    print("entered cabs at 7:30");
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    #get the current date 
    cur_date = datetime.now().date().isoformat();
    #execute the query to get the employees who are in office
    l = db_cursor.execute("SELECT emp_id, time, in_or_out FROM log_data where date='%s' ORDER BY emp_id, time DESC;"%(cur_date));
    #fetch the query results
    results =  db_cursor.fetchall();
    prev=None;
    i=0;
    emp_ids = [];
    #try to get the top 1 record if still logged in
    while(i<l):
        if(results[i][0]!=prev and results[i][2]==0):
            emp_ids.append(results[i][0]);
        prev=results[i][0];
        i=i+1;
    #check if no need to send email to anyone
    if(len(emp_ids)==0):
        print("no recepients\n");
        return;
    #execute the query to get the employee details who are in office
    l = db_cursor.execute("SELECT emp_email FROM employee_details WHERE emp_id IN (%s)"%("'"+"','".join(emp_ids)+"'"));
    #fetch the query results
    results = db_cursor.fetchall();
    email_ids = [];
    for i in results:
        email_ids.append(i[0]);
    subject = "7:30 cab request";
    body = "Hi,\n\nPlease fill in the details for cab at 7:30 in the following link\n\n https://goo.gl/forms/JVZp4UMKnrQeYKNl2 \n\nThank you.";
    send_mails(email_ids,subject,body);
    print("mails sent for cab at 7:30\n");
    

#send notification of cabs at 9:30
def cabs_at_930():
    print("entered cabs at 9:30");
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    cur_date = datetime.now().date().isoformat();
    l = db_cursor.execute("SELECT emp_id, time, in_or_out FROM log_data where date='%s' ORDER BY emp_id, time DESC;"%(cur_date));
    results = db_cursor.fetchall();
    prev=None;
    i=0;
    emp_ids = [];
    while(i<l):
        if(results[i][0]!=prev and results[i][2]==0):
            emp_ids.append(results[i][0]);
        prev=results[i][0];
        i=i+1;
    if(len(emp_ids)==0):
        print("no recepients\n");
        return;
    l = db_cursor.execute("SELECT emp_email FROM employee_details WHERE emp_id IN (%s)"%("'"+"','".join(emp_ids)+"'"));
    results = db_cursor.fetchall();
    email_ids = [];
    for i in results:
        email_ids.append(i[0]);
    subject = "9:30 cab request";
    body = "Hi,\n\nPlease fill in the details for cab at 9:30 in the following link\n\n https://goo.gl/forms/UsjnUtuVkssfmMh53 \n\nThank you.";
    send_mails(email_ids,subject,body);
    print("mails sent for cab at 9:30\n");

#send emails
def send_mails(email_send,subject,body):
    email_user = get_crd("crd//email.crd");
    email_password = get_crd("crd//password.crd");
    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = ",".join(email_send);
    msg['Subject'] = subject
    msg.attach(MIMEText(body,'plain'))
    text = msg.as_string()
    server = smtplib.SMTP(get_crd("crd//host.crd"),587);
    server.starttls()
    server.login(email_user,email_password)
    server.sendmail(email_user,email_send,text)
    server.quit()

#get credentials
def get_crd(crd):
    f = open(crd);
    s = f.readline();
    f.close();
    return base64.b64decode(s).decode('utf-8');

#update all the logs happened today into employee logs table
def update_total_logs():
    print("entered update total logs\n");
    #import pdb
    #pdb.set_trace();
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    cur_date = datetime.now().date().isoformat().replace('-','');
    #get all the logs happened today
    l=db_cursor.execute("SELECT emp_id FROM employee_details;");
    emp_ids = db_cursor.fetchall();
    for emp_id in emp_ids:
        log_id = emp_id[0] + cur_date;
        l = db_cursor.execute("SELECT time,in_or_out FROM log_data where log_id = '%s' ORDER BY time"%(log_id));
        emp_logs = db_cursor.fetchall();
        if(l==0):#absent
            db_cursor.execute("INSERT INTO employee_logs VALUES('%s','%s',NULL,NULL,'00:00:00','00:00:00')"%(emp_id[0],cur_date));
            db.commit();
            continue;
        first_login=None
        if(len(emp_logs)>1 and emp_logs[0][1]==0):
            first_login = str(emp_logs[0][0]);
        else:#forgot to login
            first_login =  get_usual_login(emp_id[0]);
        if(len(emp_logs)>1 and emp_logs[-1][1]==1):
            last_logout = str(emp_logs[-1][0]);
        else:#forgot to logout
            last_logout = get_usual_logout(emp_id[0]);
        total_time = str(get_time_difference(first_login,last_logout));
        import datetime as dt
        effective_time = dt.timedelta(0);
        i=0;
        while(i<l):
            t1 = str(emp_logs[i][0]);
            while(i<l and emp_logs[i][1]==0):
                i += 1;
            if(i>=l):
                t2 = last_logout;
                effective_time += get_time_difference(t1,t2);
                break;
            t2 = str(emp_logs[i][0]);
            effective_time += get_time_difference(t1,t2);
            i += 1;
        effective_time = str(effective_time);
        db_cursor.execute("INSERT INTO employee_logs VALUES ('%s','%s','%s','%s','%s','%s')"%(emp_id[0],cur_date,first_login,last_logout,total_time,effective_time));
        db.commit();
    print("completed updating total logs\n");


#send emails about the log updates
def send_log_updatemails():
    print("entering send log update mails\n");
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    server = smtplib.SMTP(get_crd("crd//host.crd"),587)
    server.starttls();
    email_user = get_crd("crd//email.crd");
    email_password = get_crd("crd//password.crd");
    server.login(email_user,email_password)
    cur_date = datetime.now().date().isoformat().replace('-','');
    l = db_cursor.execute("SELECT emp_id,first_login,last_logout,total_time,effective_time FROM employee_logs where date = '%s'"%(cur_date));
    results = db_cursor.fetchall();
    for i in results:
        emp_id = i[0];
        l = db_cursor.execute("SELECT emp_email,emp_name FROM employee_details WHERE emp_id = '%s'"%(emp_id));
        if(l==0):
            print("employee details does not exist %s\n"%(emp_id));
            continue;
        emp_details = db_cursor.fetchall()[0];
        emp_email = emp_details[0];
        emp_name = emp_details[1];
        first_login = i[1];
        last_logout = i[2];
        total_time = i[3];
        effective_time = i[4];
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = emp_email;
        msg['Subject'] = 'Daily log updates'
        body = "Hi %s,\n\nYour daily log reports are as follows: \n\nFirst Login: %s\n\
Last Logout: %s\nTotal Time: %s\nEffective Time: %s \n\nThank you."%(emp_name,first_login,last_logout,total_time,effective_time);
        msg.attach(MIMEText(body,'plain'))
        text = msg.as_string()
        server.sendmail(email_user,emp_email,text)
    server.quit()
    print("exiting send log update mails\n");

#get difference between times in seconds
def get_time_difference(t1,t2):
    FMT = '%H:%M:%S';
    tdelta = datetime.strptime(t2, FMT) - datetime.strptime(t1, FMT);
    return tdelta;

#get usual login
def get_usual_login(emp_id):
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    l = db_cursor.execute("SELECT first_login FROM employee_logs WHERE emp_id = '%s'"%(emp_id));
    results = db_cursor.fetchall();
    if(l == 0):
        return "09:00:00";
    result_times = list(map(lambda t: (datetime.min + t[0]).time().isoformat(),results));
    average_time = str(timedelta(seconds=sum(map(lambda f: int(f[0])*3600 + int(f[1])*60 + int(f[2]), map(lambda f: f.split(':'), result_times)))/len(resul_times)));
    return average_time;
    
#get usual logout
def get_usual_logout(emp_id):
    global db
    if(db is None and getdb() == -1):
        return;
    #generate a cursor to perform operations on database
    db_cursor = db.cursor();
    l = db_cursor.execute("SELECT last_logout FROM employee_logs WHERE emp_id = '%s'"%(emp_id));
    results = db_cursor.fetchall();
    if(l==0):
        return "18:00:00";
    result_times = list(map(lambda t: (datetime.min + t[0]).time().isoformat(),results));
    average_time = str(timedelta(seconds=sum(map(lambda f: int(f[0])*3600 + int(f[1])*60 + int(f[2]), map(lambda f: f.split(':'), result_times)))/len(resul_times)));
    return average_time;

def main():
    queue = Queue();
    #create a thread to receive the data from the scanner
    get_data_thread = threading.Thread(target=get_data,args=(queue,));
    #create a thread to process the data to database
    data_process_thread = threading.Thread(target=data_process,args=(queue,));
    #create a thread for time based activity
    time_based_activity_thread = threading.Thread(target=time_based_activity);
    #start the getdata thread
    get_data_thread.start();
    #start the data process thread
    data_process_thread.start();
    #start the timebased activity thread
    time_based_activity_thread.start();
    #join the queue - wait till the completion of all the jobs in queue
    queue.join();
    #don't quit untill all the threads are completed
    get_data_thread.join();
    data_process_thread.join();
    time_based_activity_thread.join();
    print("main is completed");

main()
