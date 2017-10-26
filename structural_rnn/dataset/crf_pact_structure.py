from collections import defaultdict

import config
from structural_rnn.dataset.graph_dataset_reader import GlobalDataSet, DataSample

if config.OPEN_CRF_CONFIG["use_pure_python"]:
    from structural_rnn.model.open_crf.pure_python.factor_graph import EdgeFactorFunction, FactorGraph
else:
    from structural_rnn.model.open_crf.cython.factor_graph import EdgeFactorFunction, FactorGraph


# this class mean to be composite of `factor_graph` and `DataSample` class which used to pass to open_crf_layer
# this class should only contains one graph_backup or one part of graph_backup which will then pass to open_crf_layer __call__ method
class CRFPackageStructure(object):

    def __init__(self, sample: DataSample, train_data: GlobalDataSet, num_attrib=None, need_s_rnn=True):

        self.sample = sample
        self.num_node = self.sample.num_node
        self.label_dict = train_data.label_dict
        self.num_label = train_data.num_label
        if num_attrib is not None:
            self.num_attrib_type = num_attrib
        else:
            self.num_attrib_type = train_data.num_attrib_type
        self.num_edge_type = train_data.num_edge_type
        self.edge_feature_offset = dict()
        self.num_edge_feature_each_type = 0
        self.num_attrib_parameter = 0
        self.num_feature = self.gen_feature()
        self.factor_graph = self.setup_factor_graph()
        self.max_bp_iter = config.OPEN_CRF_CONFIG["max_bp_iter"]
        self.node_id_convert = dict()
        if need_s_rnn:
            get_frame = lambda e: int(e[0:e.index("_")])
            get_box = lambda e: int(e[e.index("_")+1:])
            box_min_id = dict()
            for node in self.sample.node_list:
                node_key_str = self.sample.nodeid_line_no_dict.mapping_dict.inv[node.id]
                box_id = get_box(node_key_str)
                if box_id not in box_min_id:
                    box_min_id[box_id] = node
                elif get_frame(self.sample.nodeid_line_no_dict.mapping_dict.inv[box_min_id[box_id].id]) \
                        > get_frame(self.sample.nodeid_line_no_dict.mapping_dict.inv[node.id]) :
                    box_min_id[box_id] = node
            for node in self.sample.node_list:
                node_key_str = self.sample.nodeid_line_no_dict.mapping_dict.inv[node.id]
                box_id = get_box(node_key_str)
                self.node_id_convert[node.id] = box_min_id[box_id].id


            self.nodeRNN_id_dict = defaultdict(list)
            for node_id, nodeRNN_id in sorted(self.node_id_convert.items(), key=lambda e: int(e[0])):
                self.nodeRNN_id_dict[nodeRNN_id].append(node_id)


    def gen_feature(self):
        num_feature = 0
        self.num_attrib_parameter = self.num_label * self.num_attrib_type  # feature有多少种 x num_label
        num_feature += self.num_attrib_parameter
        self.edge_feature_offset.clear()
        offset = 0
        for y1 in range(self.num_label):
            for y2 in range(y1, self.num_label):
                self.edge_feature_offset[y1 * self.num_label + y2] = offset
                offset += 1
        self.num_edge_feature_each_type = offset
        num_feature += self.num_edge_type * self.num_edge_feature_each_type
        return num_feature

    def setup_factor_graph(self):  # must called after gen_feature
        func_list = []
        for i in range(self.num_edge_type):
            func_list.append(EdgeFactorFunction(num_label=self.num_label, edge_type=i,
                                                num_edge_feature_each_type=self.num_edge_feature_each_type,
                                                num_attrib_parameter=self.num_attrib_parameter,
                                                edge_feature_offset=self.edge_feature_offset))
        n = self.sample.num_node
        m = self.sample.num_edge
        factor_graph = FactorGraph(n=n, m=m, num_label=self.num_label,func_list=func_list)

        for i in range(n):  # add node info
            factor_graph.set_variable_label(i, self.sample.node_list[i].label)  # 这个label是int类型，代表字典里的数字
            factor_graph.var_node[i].label_type = self.sample.node_list[i].label_type  # ENUM的 KNOWN 或者UNKOWN

        for i in range(m):  # add edge info, mandatory. 注意a和b是int的类型的node-id
            factor_graph.add_edge(self.sample.edge_list[i].a, self.sample.edge_list[i].b,
                                  self.sample.edge_list[i].edge_type)
        if hasattr(factor_graph,"add_edge_done"):
            factor_graph.add_edge_done()
        factor_graph.gen_propagate_order()
        return factor_graph