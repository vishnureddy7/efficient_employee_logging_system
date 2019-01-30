int count = 0;
char input[13];

void setup(){
   Serial.begin(9600);
}

void loop(){
   if(Serial.available()){
      count = 0;
      while(Serial.available() && count < 12){
         input[count] = Serial.read();
         count++;
         delay(5);
      }
      Serial.println(input);
   }
}
