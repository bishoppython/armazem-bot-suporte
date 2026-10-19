"""Busca híbrida: BM25 sobre os trechos + similaridade de embeddings, combinadas por RRF.

A confiança (0 a 1) que decide o escalonamento é medida no melhor trecho:
- lexical: fração dos termos da pergunta, ponderada por IDF, que aparecem no trecho;
- semântica: cosseno entre pergunta e trecho, reescalado pelo piso e teto do modelo.
Vale o maior dos dois sinais, para que um sinônimo que o BM25 não pega não force escalonamento.
"""

import math
from collections import Counter
from collections.abc import Sequence

from bot_suporte.domain.modelos import Resultado, Trecho
from bot_suporte.domain.texto import tokens

K1 = 1.5
B = 0.75
RRF_K = 60
# Calibrado no conjunto de avaliação com o nomic-embed-text: perguntas fora do assunto chegam a
# 0,67 de cosseno máximo e as respondíveis vão de 0,62 a 0,81. O cosseno sozinho não separa os
# dois grupos; o piso só impede que ele infle a confiança. O LLM recusa o resto (FORA_DO_ESCOPO).
COS_PISO = 0.60
COS_TETO = 0.80


def cosseno(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=True))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


class IndiceBM25:
    def __init__(self, trechos: Sequence[Trecho]) -> None:
        self.trechos = list(trechos)
        self._docs = [Counter(tokens(t.texto)) for t in self.trechos]
        self._tam = [sum(c.values()) for c in self._docs]
        self._media = sum(self._tam) / len(self._tam) if self._tam else 0.0
        df: Counter[str] = Counter()
        for c in self._docs:
            df.update(c.keys())
        n = len(self.trechos)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def pontuar(self, consulta: str) -> list[float]:
        termos = tokens(consulta)
        scores = []
        for c, tam in zip(self._docs, self._tam, strict=True):
            s = 0.0
            for t in termos:
                f = c.get(t, 0)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * tam / self._media))
            scores.append(s)
        return scores

    def cobertura(self, consulta: str, i: int) -> float:
        termos = set(tokens(consulta))
        if not termos:
            return 0.0
        # Termo ausente do corpus pesa como o mais raro: pergunta fora do assunto derruba a cobertura.
        idf_max = max(self.idf.values(), default=1.0)
        total = sum(self.idf.get(t, idf_max) for t in termos)
        achados = sum(self.idf[t] for t in termos if t in self._docs[i])
        return achados / total


class Buscador:
    def __init__(
        self,
        trechos: Sequence[Trecho],
        vetores: Sequence[Sequence[float]] | None = None,
    ) -> None:
        self.bm25 = IndiceBM25(trechos)
        self.trechos = self.bm25.trechos
        self.vetores = list(vetores) if vetores is not None else None

    def buscar(
        self, consulta: str, k: int, vetor_consulta: Sequence[float] | None = None
    ) -> tuple[list[Resultado], float]:
        """Devolve os k melhores trechos e a confiança no primeiro."""
        if not self.trechos:
            return [], 0.0
        lex = self.bm25.pontuar(consulta)
        rankings = [sorted(range(len(lex)), key=lambda i: -lex[i])]
        sem: list[float] | None = None
        if self.vetores is not None and vetor_consulta is not None:
            sem = [cosseno(vetor_consulta, v) for v in self.vetores]
            rankings.append(sorted(range(len(sem)), key=lambda i: -sem[i]))

        rrf = [0.0] * len(self.trechos)
        for ranking in rankings:
            for pos, i in enumerate(ranking):
                rrf[i] += 1 / (RRF_K + pos + 1)
        # Trecho sem nenhum termo e sem embedding não entra no resultado.
        candidatos = [i for i in range(len(rrf)) if lex[i] > 0 or sem is not None]
        ordem = sorted(candidatos, key=lambda i: -rrf[i])[:k]
        if not ordem:
            return [], 0.0

        # Cada sinal é medido no seu próprio melhor trecho, não no primeiro da fusão.
        confianca = self.bm25.cobertura(consulta, max(range(len(lex)), key=lambda i: lex[i]))
        if sem is not None:
            confianca = max(confianca, _reescalar(max(sem)))
        resultados = [Resultado(self.trechos[i], rrf[i]) for i in ordem]
        return resultados, round(confianca, 3)


def _reescalar(cos: float) -> float:
    return min(1.0, max(0.0, (cos - COS_PISO) / (COS_TETO - COS_PISO)))
