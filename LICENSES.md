# Source licences and attribution

This file records licence text read from the source-project pages and the licence documents they identify. This is a technical compliance note, not legal advice. The generated pilot is a derived/combined dataset, so **do not copy it into another product until its redistribution conditions and row-level provenance have been reviewed**.

## Dicollecte / Grammalecte Hunspell French dictionary

- Official project: https://www.grammalecte.net/
- Official release archive used by the importer: https://www.grammalecte.net/dic/hunspell-french-dictionaries-v7.7.zip
- The dictionary licence notice reproduced in the Dicollecte dictionary licence file says:

> Licence :
> MPL : Mozilla Public License
> version 2.0 -- http://www.mozilla.org/MPL/2.0/

  Source text copy: https://github.com/wooorm/dictionaries/blob/master/dictionaries/fr/license
- Official licence text: https://www.mozilla.org/en-US/MPL/2.0/

Relevant exact line from the official Mozilla licence:

> This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

**Licence option:** retain MPL-2.0 for the Dicollecte resource and any covered modified files. Do not assume the entire French Academy application must be MPL solely because it uses a separate file/resource; distribution structure and derivative-work questions require review.

**Attribution/compliance:** retain the dictionary's copyright and licence notices and include the MPL-2.0 text with redistributed covered material. The Dicollecte licence notice lists contributors and points to https://grammalecte.net/members.php?prj=fr. The importer stores source URL and licence per entry; the archive's own notice should be checked against the downloaded release before release.

## Lefff 2.1

- Official project/download page: https://www.labri.fr/perso/clement/lefff/telechargement.html
- Official licence text: https://www.labri.fr/perso/clement/lefff/licence-LGPLLR.html
- Download used by the workflow: https://www.labri.fr/perso/clement/lefff/lefff-2.1.txt.gz

The published Lefff file identifies the copyright holders with this exact text:

> LEFFF version 0.2 Copyright (c) 2003,2004,2005, 2006 by Institut
> National de Recherche en Informatique et en Automatique
> Lionel Clément and Benoît Sagot

The official LGPLLR licence states:

> You may copy and distribute verbatim copies of the Linguistic Resource as you receive it, in any medium, provided that you conspicuously and appropriately publish on each copy an appropriate copyright notice and disclaimer of warranty; keep intact all the notices that refer to this License and to the absence of any warranty; and distribute a copy of this License along with the Linguistic Resource.

For modifications, the same licence states:

> The modified work must itself be a linguistic resource.

> You must cause the files modified to carry prominent notices stating that you changed the files and the date of any change.

> You must cause the whole of the work to be licensed at no charge to all third parties under the terms of this License.

**Licence option:** treat Lefff-derived linguistic-resource output as LGPLLR, not as unrestricted public-domain data. Keep the source licence with the resource. If the pilot is a derivative work under the licence, its distribution conditions may apply to the combined derived resource; get legal review before bundling it into a proprietary product.

**Attribution/compliance:** retain the copyright notice, warranty disclaimer and licence notices; distribute a copy of LGPLLR. If modifying the resource, mark the changed files and change date and license the derivative linguistic resource under LGPLLR at no charge.

## Lexique 3.83 frequency and metadata source

- Official dataset README: https://www.lexique.org/databases/Lexique383/README-Lexique.txt
- Official dataset download: https://www.lexique.org/databases/Lexique383/Lexique383.tsv
- Official licence: https://www.lexique.org/databases/Lexique383/LICENSE-CC-BY-SA4.0.txt

The official README says:

> Lexique383 est une base de données lexicales du français qui fournit
> pour ~140000 mots du français: les représentations orthographiques et
> phonémiques, les lemmes associés, la syllabation, la catégorie
> grammaticale, le genre et le nombre, les fréquences dans un corpus
> de livres et dans un corpus de sous-titres de films, etc.

It identifies the licence as:

> CC BY SA40.0

**Why included:** Dicollecte and Lefff are not frequency-ranked datasets. Lexique supplies the frequency columns and grammatical metadata needed to select the requested high-frequency pilot. The output must retain attribution to Lexique and be reviewed under CC BY-SA 4.0 share-alike conditions.

## Pilot output and combined licence caution

Each pilot row is marked `needs_review: true`, carries source and licence metadata, and includes a frequency value for audit. The output is an intersection/selection across three licensed sources. Before redistributing or integrating it, review the applicable licence obligations for each source and whether the combined selection qualifies as a derivative database or linguistic resource. Do not treat this note as a conclusion that every possible combined distribution is legally compatible.
