window.tomviz = {
  install(app) {
    app.component("tomviz-dockview-tab", {
      props: ["params"],
      setup(props) {
        const trame = window.Vue.inject("trame");
        const title = window.Vue.ref("3D View");
        const { params } = window.Vue.toRefs(props);
        return { title, params, trame };
      },
      template: `
        <trame-dataclass :instance="params.params.viewState" v-slot="{ dataclass }">
          <div class="d-flex align-center text-subtitle-1 text-no-wrap">
          <v-icon icon="mdi-stop" :color="dataclass.color" />
          {{ title }}
          <v-btn icon="mdi-trash-can-outline" variant="plain" density="compact" size="small" class="ml-2" @click="trame.trigger('remove_view', [dataclass._id])"/>
        </trame-dataclass>`,
    });
  },
};

function capitalize(string) {
  if (!string) return "";
  return string.charAt(0).toUpperCase() + string.slice(1);
}

function enableSolidColor(array_names) {
  return [
    { title: "Solid Color", value: null },
    ...array_names.map((value) => ({ title: capitalize(value), value })),
  ];
}

function treeFilter(value, search, item) {
  const node = item.raw;
  if (search.length == 0) {
    return true;
  }
  const favOnly = search.indexOf("::fav::") > -1;
  if (favOnly && !node.favorite) {
    return false;
  }
  const tokens = search
    .split(" ")
    .map((v) => v.trim().toLowerCase())
    .filter((v) => v.length && v !== "::fav::");
  if (tokens.length == 0) {
    return true;
  }
  const tags = (node.tags || []).map((v) => v.toLowerCase());
  const item_query = [node.title.toLowerCase(), ...tags].join("  ");
  return tokens.every((v) => item_query.indexOf(v) > -1);
}

window.trame.utils.tomviz = {
  capitalize,
  enableSolidColor,
  treeFilter,
};
