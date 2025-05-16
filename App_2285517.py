from itertools import count
from datetime import datetime, timedelta
import os
import re
import sys
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import numpy as np
import pytz
import phonenumbers
from flask import Flask, request, make_response
from twilio.rest import Client

app = Flask(__name__)
global twilio_number
# account_sid = os.environ['TWILIO_TEST_SID']
# auth_token = os.environ['TWILIO_TEST_TOKEN']
account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
messaging_sid = os.environ['TWILIO_MSGNG_SID']
twilio_number = "+12086034040"

client = Client(account_sid, auth_token)

# --------------------------------------------------------------------------
def get_send_time():
    timezone = pytz.timezone('America/Los_Angeles')
    now_utc = datetime.now(timezone)
    send_at = now_utc + timedelta(minutes=15, seconds = x)
    return send_at.isoformat()
# --------------------------------------------------------------------------
def send_text(text_nbr, message, now):
    global sent_texts
    global x
    if text_nbr not in sent_texts and not pd.isna(text_nbr):
        if not now:
            send_at = get_send_time()
            schedule_type = "fixed"
        else:
            send_at = None
            schedule_type = None

        try:
            message = client.messages.create(
                body=message,
                from_=twilio_number,
                to=text_nbr,
                messaging_service_sid=messaging_sid,
                send_at=send_at,
                schedule_type=schedule_type
            )
            sent_texts.add(text_nbr)
            x+=1
            return True
        except Exception as e:
            print(f"Error sending SMS to {text_nbr}: {e}")
            return False
    return False
# --------------------------------------------------------------------------
def send_voice(msg_in, data_list):
    sent_voice = set()
    calls = []
    for data in data_list:
        to_number = data.get('Phone Number')
        if to_number not in sent_voice and not pd.isna(to_number):
            try:
                msg = f"Hello {data['First_Name']},\n" + msg_in + "\n"
                call = client.calls.create(
                    twiml=f"<Response><Pause length=\"3\"/><Say voice=\"Google.en-US-Standard-J\">{msg} Goodbye. </Say></Response>",
                    to=to_number,
                    from_=twilio_number
                )
                sent_voice.add(to_number)
                calls.append(call)
                print("Voice - ", data['Last_Name'], "-", data['Phone Number']) 
            except Exception as e:
                print(f"Error sending voice call to {to_number}: {e}")
    return calls 
# --------------------------------------------------------------------------        
def send_email(subject, body, data_list):
    sent_emails = set()
    for data in data_list:
        email = data.get('Email')
        message = f"Hello {data['First_Name']},\n"
        message += body + "\n"
        if email not in sent_emails and not pd.isna(email):
            try:
                msg = MIMEMultipart()
                msg['From'] = os.environ.get('EMAIL_ADDRESS')
                msg['To'] = email
                msg['Subject'] = subject
                msg.attach(MIMEText(message, 'plain'))

                with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                    smtp.starttls()
                    smtp.login(os.environ.get('EMAIL_ADDRESS'), os.environ.get('EMAIL_PASSWORD'))
                    smtp.sendmail(msg['From'], msg['To'], msg.as_string())
                    sent_emails.add(email)
                print("Email - ", data['Last_Name'], "-", email) 
            except Exception as e:
                print(f"Error sending email to {email}: {e}")
        else:
            print(f"Invalid or missing email address for {data}")
    return len(sent_emails)
# --------------------------------------------------------------------------
def process_data(data_path):
    df = pd.read_csv(data_path)
    df_filtered = df[df['Age'] > 17]
    df_filtered = df_filtered[['First_Name', 'Last_Name', 'Phone Number']]
    df_filtered = df_filtered.dropna(subset=['Phone Number'])
    df_filtered['is_valid_phone'] = df_filtered['Phone Number'].apply(lambda x: is_valid_phone_number(x))
    df_filtered = df_filtered[df_filtered['is_valid_phone']]
    df_filtered = df_filtered.drop_duplicates(subset=['Phone Number']) 

    with open('DO_NOT_SEND_2285517.txt', 'r') as f:
        do_not_send_numbers = set(line.strip() for line in f)
    df_filtered = df_filtered[~df_filtered['Phone Number'].isin(do_not_send_numbers)]

    data_list = df_filtered.to_dict('records')
    return data_list
    
def filter_minister(data_list):
  return [record for record in data_list if record.get('Minister1')]

def filter_gender(data_list, gender):
    return [record for record in data_list if record.get('Gender') == gender]
# --------------------------------------------------------------------------    
def is_valid_phone_number(phone_number):
    try:
        parsed_number = phonenumbers.parse(phone_number, region="US")
        return phonenumbers.is_valid_number(parsed_number)
    except phonenumbers.NumberParseException:
        return False
# --------------------------------------------------------------------------
def sms_send(msg_in, data_list, now):
    success_count = 1
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        sendnow = now
        for data in data_list:
            msg = f"Hello {data['First_Name']},\n{msg_in}\n"
            future = executor.submit(send_text, data['Phone Number'], msg, sendnow)
            futures.append(future)
            print("SMS - ", data['Last_Name'], "-", data['Phone Number'])

        for future in futures:
            try:
                result = future.result()
                if result:
                    success_count += 1
            except Exception as e:
                app.logger.error(f"Error processing future: {e}")
    
    return success_count
# -------------------------------------------------------------------------- 
@app.route("/sms", methods=['POST'])        
def incoming_sms():
    authorized_list = [
        '+15099902828',
        '+15099900248'
    ]
    message_body = request.values.get('Body', None)
    global from_number
    from_number = request.values.get('From', None)
    data_file = "2285517_Master.csv"
    data_list = process_data(data_file)

    if message_body is None or from_number is None:
        return "Invalid request: Missing message body or sender number", 400

    first_word = message_body.split()[0].lower()
    msg_in = message_body.strip()
    lines = msg_in.splitlines()

    if len(lines) > 1:
        msg_in = "\n".join(lines[1:])
        
    global sent_texts        
    sent_texts = set()
    try:
        with open('DO_NOT_SEND_2285517.txt', 'r') as file:
            sent_texts = set(line.strip() for line in file)
    except FileNotFoundError:
        return "Error: DO_NOT_SEND_2285517.txt file not found.", 500

    global x
    x = 0
# --------------------------------------------------------------------------
    if first_word == "sms77216" and from_number in authorized_list:
        sms_send(msg_in, data_list, False)
        confirm_send()
        return "SMS messages scheduled.", 200
# --------------------------------------------------------------------------
    elif first_word == "cancel-sms":
        messages = client.messages.list(limit=300)  # Adjust limit as needed
        canceled_count = 0
        for message in messages:
            if message.status == 'scheduled':
                try:
                    client.messages(message.sid).update(status='canceled')
                    canceled_count += 1
                except Exception as e:
                    print(f"Error canceling message {message.sid}: {e}") 
    
        client.messages.create(
            body=f'{canceled_count} Messages canceled',
            from_='+12086034040',
            to=from_number
        )
        return f'{canceled_count} messages canceled.', 200
# --------------------------------------------------------------------------
    elif first_word == "ecs77216" and from_number in authorized_list:
        subject = "Emergency Communications System"
        send_voice(msg_in, data_list)
        sms_send(msg_in, data_list, True)
        send_email(subject, msg_in, data_list)
        confirm_send()
        return "Emergency Communications System messages sent.", 200
# --------------------------------------------------------------------------
    elif first_word == "eld2285517" and from_number in authorized_list:
        filtered_data_list = filter_gender(data_list, "M")
        
        for data in filtered_data_list:
            print(f"{x}. {data['First_Name']} {data['Last_Name']} - {data['Phone Number']}")
            msg = f"Brother {data['Last_Name']}, \n\n"
            msg += msg_in
            #send_text(data['Phone Number'], msg, False)
            print msg

        confirm_send()
        return "Messages sent successfully.", 200
# --------------------------------------------------------------------------
    elif first_word == "sis77216" and from_number in authorized_list:
        filtered_data_list = filter_gender(data_list, "F")
        
        for data in filtered_data_list:
            print(f"{x}. {data['First_Name']} {data['Last_Name']} - {data['Phone Number']}")
            msg = f"Sister {data['Last_Name']}, \n\n"
            msg += msg_in
            send_text(data['Phone Number'], msg, False)

        confirm_send()
        return "Messages sent successfully.", 200
# --------------------------------------------------------------------------
    elif first_word == "fam77216" and from_number in authorized_list:
        filtered_data_list = filter_minister(data_list)

        for x, data in enumerate(filtered_data_list, start=1): 
            if data.get('Gender') == "M":
                msg = f"Brother {data['Last_Name']}, \n\n"
            elif data.get('Gender') == "F":
                msg = f"Sister {data['Last_Name']}, \n\n"
            else: 
                msg = f"{data['First_Name']} {data['Last_Name']}, \n\n"  # Handle cases where Gender is missing or invalid
    
            msg += "Your assigned ministering brothers are as follows: \n"

            if pd.notna(data.get('Minister1')):
                msg += f"{data['Minister1']}"
                if pd.notna(data.get('Minister1_Phone')):
                    msg += f" - {data['Minister1_Phone']}"
            msg += "\n"
            
            if pd.notna(data.get('Minister2')):
                msg += f"{data['Minister2']}"
                if pd.notna(data.get('Minister2_Phone')):
                    msg += f" - {data['Minister2_Phone']}"
            msg += "\n"
            
            msg += "Feel free to reach out to them for Priesthood blessings, spiritual guidance, physical assistance or any other needs you might have. \n"
            msg += "If you are unable to reach your Ministering Brothers then please contact the member of the Elders Quorum Presidency that serves your area which is: \n"
            
            if data.get('B_District') == 'D1':
                District_Leader = "Dale Reese - 509-990-2828"
            elif data.get('B_District') == 'D2':
                District_Leader = "Ghent Bailey - 972-281-9991"
            elif data.get('B_District') == 'D3':
                District_Leader = "Glen Bailey - 208-610-3066"
                
            else:
                District_Leader = "Dale Reese - 509-990-2828"
    
            msg += f"{District_Leader}\n\n"
    
            send_text(data['Phone Number'], msg, False) 
    
        confirm_send() 
        return "Messages sent successfully.", 200
# --------------------------------------------------------------------------
    elif first_word == "min77216" and from_number in authorized_list:
        district = {
            '+15099902828': 'D1',
            '+19722819991': 'D2',
            '+12086103066': 'D3',
            '+12086102929': 'SD1',
            '+12089201618': 'SD2',
            '+15093449400': 'SD3'
        }
        district = district.get(from_number)

        try:
            df = pd.read_csv(data_file)
        except FileNotFoundError:
            return "Error: File not found.", 500
        except Exception as e:
            return f"Error reading data file: {e}", 500
        
        if district and district[0] == 'S':
            df_filtered = df[(df['S_District'] == district) & (df['Age'] > 17)]
            r = range(3, 5)  
        else:
            df_filtered = df[(df['B_District'] == district) & (df['Age'] > 17)]
            r = range(1, 3)
        
        for xr in r: 
            
            ministerxr = f"Minister{xr}"
            ministerxr_phone = f"Minister{xr}_Phone"
            ministerxr_email = f"Minister{xr}_Email"
        
            df_filtered = df_filtered[df_filtered[ministerxr].notnull()]
            df_filtered = df_filtered[df_filtered['Age'] > 17]
            df_filtered[ministerxr] = df_filtered[ministerxr].fillna('')
        
            try:
                df_filtered[['Minister_Last', 'Minister_First']] = df_filtered[ministerxr].str.split(',', expand=True) 
            except AttributeError as e:
                print(f"Error splitting {ministerxr} for potential missing or invalid data: {e}")
                continue  # Skip to the next iteration of the outer for loop
        
            grouped_df = df_filtered.groupby(["Minister_Last", "Minister_First", ministerxr_phone, ministerxr_email])
        
            for (minister_last, minister_first, minister_phone, minister_email), group in grouped_df:
          
                text_nbr = minister_phone
                subj="Your Ministering Families"
        
                if xr < 3:
                    Bro_Sis = "Brother"
                else:
                    Bro_Sis = "Sister"
                    
                msg = f"{Bro_Sis} {minister_last}, \n"
                msg += f"{msg_in} \n\n"
                msg += f"{minister_first.strip()}, just tap on the phone numbers below for options on ways to message them.\n\n"
        
                if not group.empty:
                    for index, row in group.iterrows():
                        msg += f"{row['Name']}"
                        if not pd.isna(row['Phone Number']):
                            msg += f"  - {row['Phone Number']}"
                        msg += "\n"
        
                    print(minister_phone,"  " ,minister_email,msg)
                    send_text(text_nbr, msg, False)
                    #send_email(minister_email,subj,msg)

        confirm_send()
        return "Ministering district messages sent.", 200
# --------------------------------------------------------------------------
    elif first_word == "minall77216" and from_number in authorized_list:
        try:
            try:
                df = pd.read_csv(data_file)
            except FileNotFoundError:
                return "Error: File not found.", 500
            except Exception as e:
                return f"Error reading data file: {e}", 500
    
            for r in range(1, 3):
                ministerr = f"Minister{r}"
                ministerr_phone = f"Minister{r}_Phone"
                ministerr_email = f"Minister{r}_Email"
    
                df_filtered = df[df[ministerr].notnull()]
                df_filtered = df_filtered[df_filtered['Age'] > 17]
                df_filtered[ministerr] = df_filtered[ministerr].fillna('')
    
                try:
                    df_filtered[['Minister_Last', 'Minister_FirstMiddle']] = df_filtered[ministerr].str.split(',', expand=True)
                    df_filtered['Minister_First'] = df_filtered['Minister_FirstMiddle'].str.split().str[0]
                    df_filtered = df_filtered.drop(columns=['Minister_FirstMiddle'])
                except AttributeError as e:
                    print(f"Error splitting {ministerr} for potential missing or invalid data: {e}")
                    continue
    
                grouped_df = df_filtered.groupby(["Minister_Last", "Minister_First", ministerr_phone, ministerr_email])
    
                for (minister_last, minister_first, minister_phone, minister_email), group in grouped_df:
                    text_nbr = minister_phone
                    subj = "Your Ministering Families"
    
                    if r > 2:
                        Bro_Sis = "Sister"
                    else:
                        Bro_Sis = "Brother"
    
                    msg = f"{Bro_Sis} {minister_last}, \n"
                    msg += f"{msg_in} \n\n"
                    msg += f"{minister_first.strip()}, just tap on the phone numbers below for options on ways to message them.\n\n"
    
                    if not group.empty:
                        for index, row in group.iterrows():
                            msg += f"{row['Name']}"
                            if not pd.isna(row['Phone Number']):
                                msg += f"  - {row['Phone Number']}"
                            msg += "\n"

                    if r == 1:
                        Comp = row['Minister2']
                        CompPhone = row['Minister2_Phone']
                    else:
                        Comp = row['Minister1']
                        CompPhone = row['Minister1_Phone']
                    
                    if Comp:  # Check if Comp is not None or empty
                        try:
                            Comp_Last, Comp_FirstMiddle = Comp.split(',')
                            Comp_FirstMiddle = Comp_FirstMiddle.strip()  # Clean up whitespace
                            first_name_parts = Comp_FirstMiddle.split()
                            Comp_First = first_name_parts[0]
                        except ValueError as e:
                            print(f"Value error when splitting {Comp}: {e}")
                            continue
                        except AttributeError as e:
                            print(f"Error splitting {Comp}: {e}")
                            continue
                    else:
                        print("Comp value was null")
                        continue
                    
                    if CompPhone and not pd.isna(CompPhone):  # Check if phone number exists and is not NaN
                        msg += f"\nYour Companion is {Comp_First} {Comp_Last} - {CompPhone}\n"
                    else:
                        msg += f"\nYour Companion is {Comp_First} {Comp_Last}\n"
                        
                    print(minister_last, " - ", minister_phone, "  ", minister_email, msg)
                    send_text(text_nbr, msg, False)
                    # send_email(minister_email, subj, msg)
            try:
                confirm_send()
                return "Ministering district messages sent.", 200
            except Exception as e:
                print (f"confirm send error: {e}")
                return "Error in confirm send.", 500
    
        except Exception as e:
            print(f"Main try except error: {e}")
            return "General Error", 500
# --------------------------------------------------------------------------    
    elif (first_word == "?" or first_word == "instructions") and from_number in authorized_list:
        instructions = "To send a message to any of the following groups.  Simply type the group code on the 1st line followed by your message on subsequent lines.  The message will already have a salutation on it, ie. 'Brother Jones' or 'Hello John'.  Do not use emojis or pictures.  The app is authenticated by your phone number and will only work on your phone.\n\n"
        instructions += "Group codes\n"
        instructions += "min77216 - Your Ministering District with assignments\n"
        instructions += "eld77216 - Active Adult Priesthood holders\n"
        instructions += "sms77216 - Entire Ward\n\n"
        instructions += "These messages have a 15 minute delay before they go out.  Should you choose to cancel them you may send the command 'cancel-sms' within that 15 minutes"

        message = client.messages.create(
            body= instructions,
            from_='+12086034040',
            to = from_number
            )
# --------------------------------------------------------------------------
    elif first_word == "dnc77216" and from_number in authorized_list:
        do_not_send_file = "DO_NOT_SEND.txt"
        data_file = "Westmond_Master.csv"
    
        try:
            with open(do_not_send_file, 'r') as f:
                do_not_send_numbers = set(line.strip() for line in f)
    
            df = pd.read_csv(data_file)
            matching_numbers = df[df['Phone Number'].isin(do_not_send_numbers)]
            names = matching_numbers[['First_Name', 'Last_Name']].values.tolist() 
    
        except FileNotFoundError:
            print(f"Error: File not found: {do_not_send_file} or {data_file}")
            return "Error: File not found.", 500 
        except Exception as e:
            print(f"An error occurred: {e}")
            return "An error occurred.", 500
    
        if names:
            message = "Names associated with phone numbers in DO_NOT_SEND.TXT:\n"
            for name in names:
                message += f"{name[0]} {name[1]}\n" 
            
            client.messages.create(
                body=message,
                from_=twilio_number,
                to=from_number
            )
            return "List of names sent successfully.", 200
        else:
            client.messages.create(
                body="No matching phone numbers found.",
                from_=twilio_number,
                to=from_number
            )
            return "No matching phone numbers found.", 200
# --------------------------------------------------------------------------
    else:
        
        if from_number.startswith('+1'):
            from_number = from_number[2:] 
            cleaned_number = re.sub(r'(\d{3})(\d{3})(\d{4})', r'(\1) \2-\3', from_number)
        
            df = pd.read_csv("2285517_Master.csv")
            row = df[df['Phone Number'] == cleaned_number]
        
            try:
                full_name = f"{row['First_Name'].values[0]} {row['Last_Name'].values[0]}"  
                client.messages.create(
                    body=f"{cleaned_number} - {full_name}\n{msg_in}",
                    from_=twilio_number,
                    to='+15099902828' 
                )
            except IndexError:
                client.messages.create(
                    body=f"No matching name found for {cleaned_number}",
                    from_=twilio_number,
                    to='+15099902828'
                )
            except Exception as e:
                client.messages.create(
                    body=f"An error occurred: {e}",
                    from_=twilio_number,
                    to='+15099902828'
                )
    return "Command not recognized or unauthorized.", 400
# --------------------------------------------------------------------------
def confirm_send():
    global x
    client.messages.create(
        body=f"{x} Messages scheduled. Send 'cancel-sms' within 10 mins to cancel them",
        from_=twilio_number,
        to=from_number
    )
    client.messages.create(
        body=f'{x} Messages have been scheduled by {from_number}',
        from_=twilio_number,
        to='+15099902828'
    )

if __name__ == "__main__":
    app.run()
