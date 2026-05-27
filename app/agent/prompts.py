"""Prompts por nodo — separados para facilitar iteración pedagógica."""


def planner_prompt(topic: str) -> str:
    return f"""Eres un planificador de investigación. Dado el tema, genera entre 3 y 5 subtemas concretos para investigar.

Tema: {topic}

Responde SOLO con un array JSON de strings, sin markdown ni texto extra.
Ejemplo: ["subtema 1", "subtema 2", "subtema 3"]"""


def researcher_prompt(topic: str, subtopic: str) -> str:
    return f"""Investiga el siguiente subtema en el contexto del tema principal.
Escribe un párrafo factual y claro (150-300 palabras). Si no sabes algo, dilo.

Tema principal: {topic}
Subtema: {subtopic}"""


def evaluator_prompt(topic: str, subtopic: str, content: str) -> str:
    return f"""Evalúa si esta investigación es suficientemente buena para incluirla en un reporte final.

Criterios: factual, relevante al subtema, longitud adecuada, sin relleno vacío.

Tema: {topic}
Subtema: {subtopic}
Investigación:
{content}

Responde con UNA sola palabra: SUFFICIENT o INSUFFICIENT"""


def writer_prompt(topic: str, research_results: list[dict]) -> str:
    sections = "\n\n".join(
        f"## {r['subtopic']}\n\n{r['content']}" for r in research_results
    )
    return f"""Genera un reporte final en Markdown sobre el tema.

Tema: {topic}

Usa esta investigación como base (puedes reorganizar y pulir):

{sections}

Estructura:
- Título (# )
- Resumen ejecutivo
- Secciones por subtema
- Conclusiones

Responde solo con el markdown del reporte."""
