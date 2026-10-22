import getpass, sys
import jaydebeapi

JAR = "/home/vyshu/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
URL = "jdbc:zetaris:lightning@localhost:10000"
CLASS = "com.zetaris.lightning.jdbc.LightningDriver"

conn = jaydebeapi.connect(CLASS, URL, ["admin@zetaris.com", getpass.getpass("Zetaris password: ")], JAR)
cur = conn.cursor()
for q in sys.argv[1:]:
    try:
        cur.execute(q)
        rows = cur.fetchall()
        print(q, "->", len(rows), "rows")
        for r in rows[:20]:
            print("  ", r)
    except Exception as e:
        print(q, "-> ERROR:", str(e)[:250])
conn.close()
