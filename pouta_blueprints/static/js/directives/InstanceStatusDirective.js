app.directive('instanceStatus', [function() {
    var UIDetails = {
        running: {
            iconClass: "fa-check",
            description: "instance is ready"
        },
        failed: {
            iconClass: "fa-exclamation-triangle",
            description: "instance failed"
        },
        queueing: {
            iconClass: "fa-spinner fa-spin",
            description: "hang on tight, instance is waiting to be started"
        },
        provisioning: {
            iconClass: "fa-spinner fa-spin",
            description: "almost there, instance is starting"
        },
        deleting: {
            iconClass: "fa-spinner fa-spin",
            description: "instance is being deleted"
        },
        deleted: {
            iconClass: "fa-square-o",
            description: "instance deleted"
        },
        unknown: {
            iconClass: "fa-question",
            description: "instance state unknown"
        }
    };
    return {
        restrict: 'E',
        scope: false,
        link: function(scope, element, attrs) {
            statusDetails = UIDetails[scope.instance.state];
            if (! statusDetails) {
                statusDetails = UIDetails.unknown;
            }
            scope.iconClass = statusDetails.iconClass;
            scope.description = statusDetails.description;
        },
        templateUrl: 'partials/instance_state.html'
    };
}]);
