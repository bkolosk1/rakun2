from typing import Dict, Any, Tuple, List
import numpy as np
from collections import Counter
import logging
import re
import networkx as nx
import matplotlib.pyplot as plt
import json
import pkgutil

logging.basicConfig(format='%(asctime)s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S')
logging.getLogger(__name__).setLevel(logging.INFO)


class RakunKeyphraseDetector:
    """
    The main RaKUn2.0 class
    """

    def __init__(self,
                 hyperparameters: Dict[str, Any] = {},
                 verbose: bool = True):

        self.verbose = verbose
        if self.verbose:
            logging.info("Initiated a keyword detector instance.")

        self.pattern = re.compile(r"(?u)\b\w\w+\b")
        self.hyperparameters = hyperparameters

        if "token_prune_len" not in self.hyperparameters:
            self.hyperparameters["token_prune_len"] = 1

        if "num_keywords" not in self.hyperparameters:
            self.hyperparameters["num_keywords"] = 10

        if "alpha" not in self.hyperparameters:
            self.hyperparameters["alpha"] = 0.1

        if "max_iter" not in self.hyperparameters:
            self.hyperparameters["max_iter"] = 100

        if "merge_threshold" not in self.hyperparameters:
            self.hyperparameters["merge_threshold"] = 0.5

        if "deduplication" not in self.hyperparameters:
            self.hyperparameters['deduplication'] = True

        if "stopwords" not in self.hyperparameters:

            # A collection of stopwords as default
            stopwords = pkgutil.get_data(__name__, 'stopwords.json')
            stopwords_generic = set(json.loads(stopwords.decode()))
            self.hyperparameters["stopwords"] = stopwords_generic

    def visualize_network(self,
                          labels: bool = False,
                          node_size: float = 0.1,
                          alpha: float = 0.01,
                          link_width: float = 0.01,
                          font_size: int = 3,
                          arrowsize: int = 1):
        """
        A method aimed to visualize a given token network.
        """

        if self.verbose:
            logging.info("Visualizing network")
        plt.figure(1, figsize=(10, 10), dpi=300)
        pos = nx.spring_layout(self.G, iterations=10)

        node_colors = [x[1] * 1000 for x in self.node_ranks.items()]
        sorted_top_k = np.argsort([x[1] for x in self.node_ranks.items()
                                   ])[::-1][:20]

        final_colors, final_sizes = [], []
        for enx in range(len(node_colors)):
            if enx in sorted_top_k:
                final_colors.append("red")
                final_sizes.append(node_size * 10)
            else:
                final_colors.append("gray")
                final_sizes.append(node_size)

        nx.draw_networkx_nodes(self.G,
                               pos,
                               node_size=final_sizes,
                               node_color=final_colors,
                               alpha=alpha)
        nx.draw_networkx_edges(self.G,
                               pos,
                               width=link_width,
                               arrowsize=arrowsize)

        if labels:
            nx.draw_networkx_labels(self.G,
                                    pos,
                                    font_size=font_size,
                                    font_color="red")

        plt.tight_layout()
        plt.show()

    def compute_tf_scores(self, document: str = None) -> None:

        if document is not None:
            self.tokens = self.pattern.findall(document)

        term_counter = Counter()
        for term in self.tokens:
            term_counter.update({term: 1})
        self.term_counts = dict(term_counter)
        self.sorted_terms_tf = sorted(term_counter.items(),
                                      key=lambda x: x[1],
                                      reverse=True)

    def get_document_graph(self, weight: int = 1):

        self.G = nx.DiGraph()
        num_tokens = len(self.tokens)

        for i in range(num_tokens):
            if i + 1 < num_tokens:
                node_u = self.tokens[i].lower()
                node_v = self.tokens[i + 1].lower()

                if self.G.has_edge(node_u, node_v):
                    self.G[node_u][node_v]['weight'] += weight

                else:
                    weight = weight
                    self.G.add_edge(node_u, node_v, weight=weight)

        self.G.remove_edges_from(nx.selfloop_edges(self.G))
        personalization = {a: self.term_counts[a] for a in self.tokens}

        if len(self.G) > self.hyperparameters['num_keywords']:
            self.node_ranks = \
                nx.pagerank(self.G, alpha=self.hyperparameters["alpha"],
                            max_iter=self.hyperparameters["max_iter"],
                            personalization=personalization).items()

            self.node_ranks = [[k, v] for k, v in self.node_ranks]
        else:

            self.node_ranks = [[k, 1.0] for k in self.G.nodes()]

        token_list = [k for k, v in self.node_ranks]
        rank_distribution = np.array([y for x, y in self.node_ranks])
        token_length_distribution = np.array(
            [len(x) for x, y in self.node_ranks])

        final_scores = rank_distribution * token_length_distribution
        self.node_ranks = dict(zip(token_list, final_scores))

    def parse_input(self, document: str, input_type: str) -> None:

        if input_type == "file":
            with open(document, "r", encoding="utf-8") as doc:
                full_document = doc.read().split("\n")

        elif input_type == "string":
            if type(document) == list:
                return document

            elif type(document) == str:
                full_document = document.split("\n")

        return full_document

    def combine_keywords(self) -> None:
        """
        The keyword combination method. Individual keywords
        are combined if needed.
        Some deduplication also happens along the way.
        """

        combined_keywords = []
        appeared_tokens = {}

        for ranked_node, score in self.node_ranks.items():

            if ranked_node.lower() in self.hyperparameters['stopwords'] \
               or len(ranked_node) <= 2:
                continue

            if ranked_node not in appeared_tokens:
                ranked_tuple = [ranked_node, score]
                combined_keywords.append(ranked_tuple)

            appeared_tokens[ranked_node] = 1

        sorted_keywords = sorted(combined_keywords,
                                 key=lambda x: x[1],
                                 reverse=True)

        self.final_keywords = sorted_keywords

    def merge_tokens(self) -> None:

        two_grams = [(self.tokens[enx], self.tokens[enx + 1])
                     for enx in range(len(self.tokens) - 1)]
        self.bigram_counts = dict(Counter(two_grams))
        tmp_tokens = []
        merged = set()
        for enx in range(len(self.tokens) - 1):
            token1 = self.tokens[enx]
            token2 = self.tokens[enx + 1]

            count1 = self.term_counts[token1]
            count2 = self.term_counts[token2]

            bgc = self.bigram_counts[(token1, token2)]
            bgs = np.abs(count1 - bgc) + np.abs(count2 - bgc)
            bgs = bgs / (count1 + count2)

            if token1 not in self.hyperparameters['stopwords'] and \
               token2 not in self.hyperparameters['stopwords']:

                if bgs < self.hyperparameters['merge_threshold']:
                    if len(token2) > \
                       self.hyperparameters['token_prune_len'] and \
                       len(token1) > self.hyperparameters['token_prune_len']:

                        to_add = token1 + " " + token2
                        tmp_tokens.append(to_add)

                        merged.add(token1)
                        merged.add(token2)

                        self.term_counts[to_add] = bgc
                        self.term_counts[token1] *= self.hyperparameters[
                            'merge_threshold']

                        self.term_counts[token2] *= self.hyperparameters[
                            'merge_threshold']
                else:
                    continue

            else:
                tmp_tokens.append(token1)
                tmp_tokens.append(token2)

        # remove duplicate entries
        if self.hyperparameters['deduplication']:
            to_drop = []

            for token in tmp_tokens:
                if token in merged:
                    to_drop.append(token)

            to_drop = set(to_drop)
            tmp_tokens = [x for x in tmp_tokens if x not in to_drop]

        self.tokens = tmp_tokens

    def tokenize(self) -> None:

        whitespace_count = self.document.count(" ")
        self.full_tokens = self.pattern.findall(self.document)

        if len(self.full_tokens) > 0:
            space_factor = whitespace_count / len(self.full_tokens)

        else:
            space_factor = 0

        if space_factor < 0.5:

            self.tokens = [x for x in list(self.document.strip()) if
                           not x == " "
                           and not x == "\n"
                           and not x == "，"]

            self.tokens = [x for x in self.tokens if not x.isdigit()
                           and " " not in x]

        else:
            self.tokens = [x for x in self.full_tokens if not x.isdigit()]
            del self.full_tokens

    def find_keywords(self,
                      document: str,
                      input_type: str = "file") -> List[Tuple[str, float]]:
        """
        The main method responsible calling the child methods, yielding
        the final set of (ranked) keywords.
        """

        document = self.parse_input(document, input_type=input_type)
        self.document = " ".join(document)
        self.tokenize()
        self.compute_tf_scores()
        self.merge_tokens()
        self.get_document_graph()
        self.combine_keywords()
        return self.final_keywords[:self.hyperparameters['num_keywords']]
