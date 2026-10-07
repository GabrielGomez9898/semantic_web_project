from rdflib import Graph

archivo = "../../dataset/modelo_conceptual/instances.ttl"

g = Graph()

try:
    g.parse(archivo, format="turtle")

    print("Validando:", archivo)
    print("✅ instances.ttl tiene sintaxis Turtle válida")
    print("📊 Triples encontrados:", len(g))

except Exception as e:
    print("Validando:", archivo)
    print("❌ instances.ttl tiene errores de sintaxis")
    print("Error:")
    print(e)