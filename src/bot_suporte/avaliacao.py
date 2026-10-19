"""Conjunto de avaliação: recuperação, escalonamento e fidelidade às fontes."""

import json
import time
from pathlib import Path
from typing import Any

from bot_suporte.config import Config
from bot_suporte.servico import Atendente


def avaliar(config: Config, arquivo: Path) -> dict[str, Any]:
    casos = [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines() if linha.strip()]
    at = Atendente.a_partir_da_config(config)
    linhas = []
    for caso in casos:
        inicio = time.perf_counter()
        _, r = at.responder(caso["pergunta"], canal="avaliacao")
        segundos = time.perf_counter() - inicio
        resultados, _ = at.buscar(caso["pergunta"])
        docs = [res.trecho.doc for res in resultados]
        esperado = caso.get("doc")
        deve_escalar = bool(caso.get("escala", False))
        deve_recusar = bool(caso.get("recusa", False))
        # Fora do assunto: recusar é o ideal; escalar (pelo limiar) também é seguro. Em "vocês vendem X?"
        # (ou_nega), responder que não vende também está certo.
        if deve_recusar:
            nega = bool(caso.get("ou_nega")) and "não" in r.texto.lower()
            decisao_ok = r.fora_do_escopo or r.escalou or nega
        else:
            decisao_ok = r.escalou == deve_escalar and not r.fora_do_escopo
        termos = caso.get("contem", [])
        texto = r.texto.lower()
        linhas.append(
            {
                "pergunta": caso["pergunta"],
                "doc_esperado": esperado,
                "docs": docs,
                "recuperou": None if esperado is None else esperado in docs,
                "top1": None if esperado is None else bool(docs) and docs[0] == esperado,
                "escalou": r.escalou,
                "motivo": r.motivo_escalonamento,
                "recusou": r.fora_do_escopo,
                "decisao_ok": decisao_ok,
                "fiel": None
                if r.escalou or r.fora_do_escopo or not termos
                else all(t.lower() in texto for t in termos),
                "confianca": r.confianca,
                "resposta": r.texto,
                "segundos": round(segundos, 2),
                "tokens": r.uso.tokens_entrada + r.uso.tokens_saida,
            }
        )

    def taxa(chave: str) -> float:
        vals = [linha[chave] for linha in linhas if linha[chave] is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    metricas = {
        "casos": len(linhas),
        "recuperacao_top_k": taxa("recuperou"),
        "recuperacao_top_1": taxa("top1"),
        "decisao_correta": taxa("decisao_ok"),
        "fidelidade": taxa("fiel"),
        "taxa_escalonamento": round(sum(linha["escalou"] for linha in linhas) / len(linhas), 3),
        "taxa_recusa": round(sum(linha["recusou"] for linha in linhas) / len(linhas), 3),
        "segundos_medio": round(sum(linha["segundos"] for linha in linhas) / len(linhas), 2),
        "tokens_total": sum(linha["tokens"] for linha in linhas),
    }
    pesos = {"recuperacao_top_k": 0.3, "decisao_correta": 0.4, "fidelidade": 0.3}
    if config.modo_demo:
        pesos = {"recuperacao_top_k": 0.5, "decisao_correta": 0.5}
    metricas["nota_geral"] = round(sum(metricas[k] * p for k, p in pesos.items()) / sum(pesos.values()), 3)
    return {"metricas": metricas, "casos": linhas}
