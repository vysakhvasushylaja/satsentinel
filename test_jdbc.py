import getpass
import jaydebeapi

JAR = "/home/vyshu/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
URL = "jdbc:zetaris:lightning@localhost:10000"
CLASS = "com.zetaris.lightning.jdbc.LightningDriver"

user = "admin@zetaris.com"
password = getpass.getpass("Zetaris password: ")

conn = jaydebeapi.connect(CLASS, URL, [user, password], JAR)
cur = conn.cursor()
cur.execute("SELECT 1")
print("RESULT:", cur.fetchall())
cur.close()
conn.close()
