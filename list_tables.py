import getpass
import jaydebeapi

JAR = "/home/vyshu/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
URL = "jdbc:zetaris:lightning@localhost:10000"
CLASS = "com.zetaris.lightning.jdbc.LightningDriver"

conn = jaydebeapi.connect(CLASS, URL, ["admin@zetaris.com", getpass.getpass("Zetaris password: ")], JAR)
cur = conn.cursor()
for q in ["SHOW DATABASES", "SHOW TABLES"]:
    try:
        cur.execute(q)
        print(q, "->", cur.fetchall())
    except Exception as e:
        print(q, "-> ERROR:", str(e)[:300])
conn.close()
