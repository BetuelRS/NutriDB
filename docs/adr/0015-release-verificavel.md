# ADR-0015 - Release verificável: SBOM, atestação e assinatura

- **Estado**: Aprovado
- **Data**: 2026-08-20
- **Fase**: P2/F7 - release verificável

---

## 1. Contexto

O ADR-0013 entregou o manifesto `release-1` e `SHA256SUMS`, mas um
consumidor externo não consegue ainda: (a) validar a lista de componentes
e licenças num formato standard (SBOM); (b) saber qual o commit, o
ambiente e a hora de cada release (atestação); (c) autenticar a origem do
release (assinatura). A regra P5 exige determinismo byte-a-byte exceto o
bloco temporal `build_metadata`; qualquer novo ficheiro de release tem de
respeitar essa fronteira.

## 2. Decisão

Cada build produzirá, além do manifesto (ADR-0013), três novos ficheiros
no diretório de artefactos:

1. **`<artefacto>.sbom.json`** — SBOM CycloneDX 1.6, determinístico:
   - `serialNumber` = `urn:uuid:` + UUID5 derivado do SHA-256 do artefacto
     (sem aleatoriedade);
   - sem `metadata.timestamp` (determinismo P5);
   - componente raiz: o artefacto SQLite (`type: file`, com hash SHA-256);
   - um componente `type: data` por fonte do registry, com versão, licenças
     (SPDX quando conhecida; `UNKNOWN` honesto quando não), atribuição e
     hashes SHA-256 dos ficheiros fixados;
   - `dependencies`: artefacto -> fontes.

2. **`<artefacto>.attestation.json`** — schema `attestation-1`,
   **não-determinístico por desenho** (contém o bloco temporal):
   - `subject`: o artefacto (nome + SHA-256);
   - `digests`: SHA-256 do artefacto, manifesto, SBOM, `SHA256SUMS` e
     `metrics.json` de QA;
   - `build_metadata`: commit e branch git, versão uv, plataforma, `CI`
     (bool) e timestamp UTC ISO — o único bloco temporal, espelho do que o
     package grava no SQLite;
   - `signature`: `null` ou `{"algorithm": "Ed25519", "value": <base64>}`.

3. **Assinatura Ed25519** da atestação (bytes exatos do ficheiro) com a
   chave privada lida de `NUTRIDB_SIGNING_KEY` (PEM PKCS8 ou seed raw
   base64 de 32 bytes). Sem variável: atestação fica assinada como `null`
   e o build avisa. Variável presente mas inválida: **fail high** (P9) —
   nunca publicar um release com assinatura potencialmente corrompida.

O `SHA256SUMS` (ADR-0013) passa a cobrir apenas os ficheiros
determinísticos: artefacto, manifesto e SBOM. A atestação não entra nos
checksums porque o seu hash varia com o bloco temporal; os seus `digests`
internos é que fixam os restantes ficheiros. Nota: artefacto, manifesto e
SBOM embutem impressões digitais do hash físico do artefacto (que inclui o
bloco temporal); no gate de determinismo essas referências são apagadas
(sentinelas) antes da comparação — o que se prova é o conteúdo
determinístico, não os fingerprints do bloco temporal.

Novo comando **`nutridb release verify <artefacto>`**: verifica os hashes
do artefacto contra o manifesto, `SHA256SUMS` e SBOM; verifica os digests
internos da atestação; se a atestação estiver assinada e for fornecida a
chave pública (`--public-key <pem>` ou `NUTRIDB_PUBLIC_KEY`), verifica a
assinatura — falha alto em qualquer mismatch; atestação assinada sem chave
pública gera aviso (não falha).

**Dependência nova**: `cryptography` (runtime) para Ed25519 — a única
alteração de stack do projeto; justificada por esta decisão (regra 4 das
regras de trabalho).

## 3. Consequências

- Um consumidor pode validar componentes/licenças em formato standard,
  ligar o release ao commit e, com a chave pública, autenticar a origem.
- O SBOM mantém o determinismo P5; a atestação isola todo o bloco temporal
  num ficheiro próprio, sem tocar no artefacto.
- Releases sem `NUTRIDB_SIGNING_KEY` são verificáveis em integridade mas
  não autenticáveis; o gate de determinismo do CI compara agora também
  manifesto, SBOM e `SHA256SUMS` (na forma normalizada — ver nota nos
  checksums).
- A chave privada é âncora de confiança humana: o seu manuseamento (onde
  guardar, quem a detém) fica fora do repositório e é decidido pelo
  mantenedor aquando da primeira assinatura pública.