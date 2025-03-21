
current_operator = None
IS_TRACING = True

def report(msg, reportType="WARNING"):
    if current_operator is not None:
        current_operator.report(set((reportType, )), msg)
    print("{} ({})".format(msg, reportType))

def trace(msg):
    if IS_TRACING:
        print(msg)
