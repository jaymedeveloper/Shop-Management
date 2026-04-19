import psycopg2

def db():
    return psycopg2.connect("postgresql://neondb_owner:npg_N1CIiUM8ySmb@ep-withered-hill-ammtqm5f.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require")