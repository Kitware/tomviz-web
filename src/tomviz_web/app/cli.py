def configure(parser):
    """Add the application's arguments to trame's parser (once: a server may
    host several apps in one process, e.g. under tests) and parse them."""
    if "--catalog" in parser._option_string_actions:
        args, _ = parser.parse_known_args()
        return args
    parser.add_argument(
        "--catalog",
        "--operators",  # former name, kept so existing launch scripts work
        dest="catalog",
        help="Path to the catalog configuration file (scanned directories and "
        "modules, favorites); default: ~/.tomviz/catalog.json",
    )
    parser.add_argument(
        "--settings",
        help="Path to the user settings file (UI preferences); "
        "default: ~/.tomviz/settings.json",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Never write the catalog configuration (favorites) nor the settings file",
    )
    args, _ = parser.parse_known_args()
    return args
